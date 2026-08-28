package io.elmos.persistence;

import static io.elmos.persistence.SqlTimestamps.offset;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.workflow.CheckpointForkPolicy;
import io.elmos.workflow.PaymentSettlementReconciler;
import io.elmos.workflow.TaskFinopsAnalytics;
import io.elmos.workflow.TaskFinopsOperationsPort;
import io.elmos.workflow.TaskFinopsPolicy;
import io.elmos.workflow.TaskFinopsPort;
import io.elmos.workflow.TenantLifecyclePolicy;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;

/** PostgreSQL adapter for the V77.1/V77.2 fail-closed operations. */
public final class JdbcTaskFinopsOperationsStore implements TaskFinopsOperationsPort {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final TransactionTemplate analyticsTransactions;
    private final ObjectMapper json;

    public JdbcTaskFinopsOperationsStore(
            JdbcClient jdbc,
            TransactionTemplate transactions,
            ObjectMapper json
    ) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.analyticsTransactions = new TransactionTemplate(Objects.requireNonNull(
                transactions.getTransactionManager(), "transactionManager"));
        this.analyticsTransactions.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        this.analyticsTransactions.setIsolationLevel(
                TransactionDefinition.ISOLATION_REPEATABLE_READ);
        this.json = Objects.requireNonNull(json, "json");
    }

    @Override
    public long setFeatureRollout(FeatureRolloutCommand command) {
        Objects.requireNonNull(command, "command");
        return inContext(command.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_set_feature_rollout(
                    cast(:environment as varchar), cast(:feature as varchar),
                    cast(:stage as varchar), cast(:exposurePercent as smallint),
                    cast(:expectedVersion as bigint),
                    cast(:idempotencyKey as varchar), cast(:requestDigest as varchar))
                """)
                .param("environment", command.environment().name())
                .param("feature", command.featureKey())
                .param("stage", command.stage().name())
                .param("exposurePercent", command.exposurePercent())
                .param("expectedVersion", command.expectedVersion())
                .param("idempotencyKey", command.idempotencyKey())
                .param("requestDigest", command.requestDigest())
                .query(Long.class).single()));
    }

    @Override
    public String recordCheckpointCompatibility(CheckpointCompatibilityCommand command) {
        Objects.requireNonNull(command, "command");
        String[] reasons = command.reasonCodes().stream()
                .map(CheckpointForkPolicy.ReasonCode::name).toArray(String[]::new);
        return inContext(command.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_record_checkpoint_compatibility(
                    cast(:decisionId as varchar), cast(:checkpointId as varchar),
                    cast(:decisionState as varchar), cast(:fingerprintDigest as varchar),
                    cast(:reasonCodes as text[]), cast(:evidenceDigest as varchar),
                    cast(:signatureAlgorithm as varchar), cast(:signingKeyId as varchar),
                    cast(:signature as varchar))
                """)
                .param("decisionId", command.decisionId())
                .param("checkpointId", command.checkpointId())
                .param("decisionState", command.databaseDecision())
                .param("fingerprintDigest", command.fingerprintDigest())
                .param("reasonCodes", reasons)
                .param("evidenceDigest", command.evidenceDigest())
                .param("signatureAlgorithm", command.signatureAlgorithm())
                .param("signingKeyId", command.signingKeyId())
                .param("signature", command.signature())
                .query(String.class).single()));
    }

    @Override
    public RecoveryForkResult forkRecovery(ForkRecoveryCommand command) {
        Objects.requireNonNull(command, "command");
        return inContext(command.context(), () -> domain(() -> {
            String child = jdbc.sql("""
                    select elmos_mtf_fork_incompatible_recovery(
                        cast(:recoveryId as varchar), cast(:parentTaskId as varchar),
                        cast(:checkpointId as varchar), cast(:decisionId as varchar),
                        cast(:childTaskId as varchar), cast(:idempotencyKey as varchar),
                        cast(:requestDigest as varchar))
                    """)
                    .param("recoveryId", command.recoveryForkId())
                    .param("parentTaskId", command.parentTaskId())
                    .param("checkpointId", command.checkpointId())
                    .param("decisionId", command.compatibilityDecisionId())
                    .param("childTaskId", command.childTaskId())
                    .param("idempotencyKey", command.idempotencyKey())
                    .param("requestDigest", command.requestDigest())
                    .query(String.class).single();
            return jdbc.sql("""
                    select recovery_fork_id, parent_job_id, checkpoint_id,
                           compatibility_decision_id, child_job_id,
                           parent_run_number, child_run_number, created_at
                      from task_recovery_forks
                     where child_job_id = :childTaskId
                    """)
                    .param("childTaskId", child)
                    .query((rs, row) -> new RecoveryForkResult(
                            rs.getString("recovery_fork_id"),
                            rs.getString("parent_job_id"),
                            rs.getString("checkpoint_id"),
                            rs.getString("compatibility_decision_id"),
                            rs.getString("child_job_id"),
                            rs.getLong("parent_run_number"),
                            rs.getLong("child_run_number"),
                            instant(rs, "created_at")))
                    .single();
        }));
    }

    @Override
    public String requestLifecycle(LifecycleRequestCommand command) {
        Objects.requireNonNull(command, "command");
        return inContext(command.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_request_tenant_lifecycle(
                    cast(:jobId as varchar), cast(:operation as varchar),
                    cast(:format as varchar), cast(:retentionCutoff as timestamptz),
                    cast(:idempotencyKey as varchar), cast(:requestDigest as varchar))
                """)
                .param("jobId", command.lifecycleJobId())
                .param("operation", command.operation().name())
                .param("format", command.exportFormat().name())
                .param("retentionCutoff", offset(command.retentionCutoff()))
                .param("idempotencyKey", command.idempotencyKey())
                .param("requestDigest", command.requestDigest())
                .query(String.class).single()));
    }

    @Override
    public Optional<LifecycleStatus> lifecycleStatus(
            TaskFinopsPort.AuthenticatedContext context,
            String lifecycleJobId
    ) {
        Objects.requireNonNull(context, "context");
        require(lifecycleJobId, "LIFECYCLE_JOB");
        return inContext(context, () -> jdbc.sql("""
                select lifecycle_job_id, organization_id, account_id,
                       operation_kind, export_format, operation_state,
                       retention_cutoff, page_cursor, manifest_digest,
                       exported_row_count, exported_byte_count,
                       provider_result_state, failure_code, state_version,
                       requested_at, completed_at
                  from task_tenant_lifecycle_jobs
                 where lifecycle_job_id = :jobId
                   and organization_id = :organization
                   and account_id = :account
                """)
                .param("jobId", lifecycleJobId)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .query(this::readLifecycleStatus)
                .optional());
    }

    @Override
    public long advanceLifecycle(LifecycleTransitionCommand command) {
        Objects.requireNonNull(command, "command");
        String providerState = command.providerResult().name();
        return inContext(command.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_advance_tenant_lifecycle(
                    cast(:jobId as varchar), cast(:expectedVersion as bigint),
                    cast(:nextState as varchar), cast(:pageCursor as varchar),
                    cast(:manifestDigest as varchar), cast(:rowCount as bigint),
                    cast(:byteCount as bigint), cast(:providerState as varchar),
                    cast(:failureCode as varchar), cast(:idempotencyKey as varchar),
                    cast(:requestDigest as varchar))
                """)
                .param("jobId", command.lifecycleJobId())
                .param("expectedVersion", command.expectedVersion())
                .param("nextState", command.nextState())
                .param("pageCursor", command.pageCursor())
                .param("manifestDigest", command.manifestDigest())
                .param("rowCount", command.rowCount())
                .param("byteCount", command.byteCount())
                .param("providerState", providerState)
                .param("failureCode", command.failureCode())
                .param("idempotencyKey", command.idempotencyKey())
                .param("requestDigest", command.requestDigest())
                .query(Long.class).single()));
    }

    @Override
    public long checkpointExportPage(ExportPageCommand command) {
        Objects.requireNonNull(command, "command");
        return inContext(command.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_checkpoint_tenant_export_page(
                    cast(:jobId as varchar), cast(:pageNumber as bigint),
                    cast(:cursorDigest as varchar), cast(:rowCount as bigint),
                    cast(:byteCount as bigint), cast(:cumulativeRows as bigint),
                    cast(:cumulativeBytes as bigint), cast(:terminal as boolean),
                    cast(:pageDigest as varchar), cast(:expectedVersion as bigint),
                    cast(:idempotencyKey as varchar), cast(:requestDigest as varchar))
                """)
                .param("jobId", command.lifecycleJobId())
                .param("pageNumber", command.pageNumber())
                .param("cursorDigest", command.cursorDigest())
                .param("rowCount", command.rowCount())
                .param("byteCount", command.byteCount())
                .param("cumulativeRows", command.cumulativeRowCount())
                .param("cumulativeBytes", command.cumulativeByteCount())
                .param("terminal", command.terminal())
                .param("pageDigest", command.pageDigest())
                .param("expectedVersion", command.expectedVersion())
                .param("idempotencyKey", command.idempotencyKey())
                .param("requestDigest", command.requestDigest())
                .query(Long.class).single()));
    }

    @Override
    public long recordPurgeResult(PurgeResultCommand command) {
        Objects.requireNonNull(command, "command");
        return inContext(command.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_record_tenant_purge_result(
                    cast(:receiptId as varchar), cast(:jobId as varchar),
                    cast(:objectId as varchar), cast(:providerResult as varchar),
                    cast(:providerReference as varchar), cast(:evidenceDigest as varchar),
                    cast(:expectedVersion as bigint), cast(:idempotencyKey as varchar),
                    cast(:requestDigest as varchar))
                """)
                .param("receiptId", command.purgeReceiptId())
                .param("jobId", command.lifecycleJobId())
                .param("objectId", command.contentObjectId())
                .param("providerResult", command.providerResult())
                .param("providerReference", command.providerReference())
                .param("evidenceDigest", command.evidenceDigest())
                .param("expectedVersion", command.expectedVersion())
                .param("idempotencyKey", command.idempotencyKey())
                .param("requestDigest", command.requestDigest())
                .query(Long.class).single()));
    }

    @Override
    public SettlementReceipt recordSettlement(SettlementCommand command) {
        Objects.requireNonNull(command, "command");
        PaymentSettlementReconciler.ReconciliationRequest request = command.reconciliation();
        PaymentSettlementReconciler.ReconciliationResult result =
                PaymentSettlementReconciler.reconcile(request);
        var ledger = request.ledgerSettlement();
        var provider = request.providerSettlement();
        java.math.BigDecimal providerNet = provider.amounts() == null
                ? null : provider.amounts().netMinor();
        String providerState = switch (provider.outcome()) {
            case CONFIRMED -> "CONFIRMED";
            case REJECTED -> "FAILED";
            case UNKNOWN -> "UNKNOWN";
        };
        return inContext(command.context(), () -> domain(() -> {
            String id = jdbc.sql("""
                    select elmos_mtf_record_settlement_reconciliation(
                        cast(:reconciliationId as varchar), cast(:provider as varchar),
                        cast(:providerReference as varchar), cast(:periodStart as timestamptz),
                        cast(:periodEnd as timestamptz), cast(:currency as varchar),
                        cast(:providerReported as numeric), cast(:ledgerRecorded as numeric),
                        cast(:providerState as varchar), cast(:evidenceDigest as varchar),
                        cast(:verifierActor as varchar), cast(:idempotencyKey as varchar),
                        cast(:requestDigest as varchar))
                    """)
                    .param("reconciliationId", request.reconciliationId())
                    .param("provider", command.provider())
                    .param("providerReference", provider.providerReference())
                    .param("periodStart", offset(ledger.period().startInclusive()))
                    .param("periodEnd", offset(ledger.period().endExclusive()))
                    .param("currency", ledger.currency())
                    .param("providerReported", providerNet)
                    .param("ledgerRecorded", ledger.amounts().netMinor())
                    .param("providerState", providerState)
                    .param("evidenceDigest", command.externalEvidenceDigest())
                    .param("verifierActor", command.evidenceVerifierActorId())
                    .param("idempotencyKey", command.idempotencyKey())
                    .param("requestDigest", command.requestDigest())
                    .query(String.class).single();
            SettlementReceipt receipt = jdbc.sql("""
                    select settlement_reconciliation_id, reconciliation_state,
                           currency, period_start, period_end,
                           provider_reported_minor, ledger_recorded_minor,
                           difference_minor, recorded_at
                      from task_settlement_reconciliations
                     where settlement_reconciliation_id = :id
                    """)
                    .param("id", id)
                    .query((rs, row) -> new SettlementReceipt(
                            rs.getString("settlement_reconciliation_id"),
                            settlementStatus(rs.getString("reconciliation_state")),
                            rs.getString("currency"),
                            instant(rs, "period_start"), instant(rs, "period_end"),
                            rs.getBigDecimal("provider_reported_minor"),
                            rs.getBigDecimal("ledger_recorded_minor"),
                            rs.getBigDecimal("difference_minor"),
                            instant(rs, "recorded_at")))
                    .single();
            requireSettlementParity(receipt, request, result, providerNet);
            return receipt;
        }));
    }

    @Override
    public AnalyticsSource analyticsSource(AnalyticsWindow window) {
        Objects.requireNonNull(window, "window");
        // journal() and financialFacts() join this REPEATABLE_READ transaction
        // through the same transaction manager, so both lists share one source
        // snapshot even though their scope rules remain independently bounded.
        return inAnalyticsContext(window.context(), () ->
                new AnalyticsSource(journal(window), financialFacts(window)));
    }

    @Override
    public List<TaskFinopsAnalytics.JournalEvent> journal(AnalyticsWindow window) {
        Objects.requireNonNull(window, "window");
        return inContext(window.context(), () -> {
            List<TaskFinopsAnalytics.JournalEvent> rows = jdbc.sql("""
                    select organization_id, account_id, task_id, run_number,
                           event_sequence, event_id, task_state,
                           progress_percent, occurred_at
                      from mtf_task_journal_for_rebuild
                     where occurred_at < cast(:windowEnd as timestamptz)
                     order by task_id, run_number, event_sequence, event_id
                     limit :limit
                    """)
                    .param("windowEnd", offset(window.windowEnd()))
                    .param("limit", window.limit() + 1)
                    .query((rs, row) -> new TaskFinopsAnalytics.JournalEvent(
                            rs.getString("organization_id"), rs.getString("account_id"),
                            rs.getString("task_id"), rs.getLong("run_number"),
                            rs.getLong("event_sequence"), rs.getString("event_id"),
                            enumValue(TaskFinopsPolicy.TaskState.class,
                                    rs.getString("task_state"), "TASK_STATE"),
                            rs.getShort("progress_percent"), instant(rs, "occurred_at")))
                    .list();
            return bounded(rows, window.limit());
        });
    }

    @Override
    public List<TaskFinopsAnalytics.FinancialFact> financialFacts(AnalyticsWindow window) {
        Objects.requireNonNull(window, "window");
        return inContext(window.context(), () -> {
            List<TaskFinopsAnalytics.FinancialFact> rows = jdbc.sql("""
                    select organization_id, account_id, task_id, run_number,
                           fact_id, workload_class, currency, allocation_basis,
                           cost_delta_minor, revenue_delta_minor, occurred_at,
                           completeness, reconciliation_status
                      from mtf_task_financial_facts_for_rebuild
                     where occurred_at >= cast(:windowStart as timestamptz)
                       and occurred_at < cast(:windowEnd as timestamptz)
                     order by occurred_at, task_id, run_number, fact_id
                     limit :limit
                    """)
                    .param("windowStart", offset(window.windowStart()))
                    .param("windowEnd", offset(window.windowEnd()))
                    .param("limit", window.limit() + 1)
                    .query((rs, row) -> new TaskFinopsAnalytics.FinancialFact(
                            rs.getString("organization_id"), rs.getString("account_id"),
                            rs.getString("task_id"), rs.getLong("run_number"),
                            rs.getString("fact_id"),
                            enumValue(TaskFinopsPolicy.WorkloadClass.class,
                                    rs.getString("workload_class"), "WORKLOAD_CLASS"),
                            rs.getString("currency"),
                            enumValue(TaskFinopsPort.AllocationBasis.class,
                                    rs.getString("allocation_basis"), "ALLOCATION_BASIS"),
                            rs.getBigDecimal("cost_delta_minor"),
                            rs.getBigDecimal("revenue_delta_minor"),
                            instant(rs, "occurred_at"),
                            enumValue(TaskFinopsAnalytics.DataCompleteness.class,
                                    rs.getString("completeness"), "COMPLETENESS"),
                            enumValue(TaskFinopsPort.ReconciliationStatus.class,
                                    rs.getString("reconciliation_status"),
                                    "RECONCILIATION_STATUS")))
                    .list();
            return bounded(rows, window.limit());
        });
    }

    @Override
    public long currentProjectionGeneration(TaskFinopsPort.AuthenticatedContext context) {
        Objects.requireNonNull(context, "context");
        return inContext(context, () -> jdbc.sql("""
                select generation_version
                  from task_finops_projection_heads
                 where organization_id = :organization and account_id = :account
                """)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .query(Long.class).optional().orElse(0L));
    }

    @Override
    public long publishProjection(ProjectionPublication publication) {
        Objects.requireNonNull(publication, "publication");
        List<Map<String, Object>> buckets = new ArrayList<>();
        publication.hourly().rows().forEach(row -> buckets.add(bucketJson(row)));
        publication.daily().rows().forEach(row -> buckets.add(bucketJson(row)));
        List<Map<String, Object>> runs = publication.journal().runs().stream()
                .map(this::runJson).toList();
        Instant sourceAsOf = max(publication.journal().asOf(),
                max(publication.hourly().asOf(), publication.daily().asOf()));
        return inContext(publication.context(), () -> domain(() -> jdbc.sql("""
                select elmos_mtf_publish_analytics_projection(
                    cast(:rebuildId as varchar), cast(:windowStart as timestamptz),
                    cast(:windowEnd as timestamptz), cast(:expectedGeneration as bigint),
                    cast(:eventCount as bigint), cast(:factCount as bigint),
                    cast(:journalChecksum as varchar), cast(:hourlyChecksum as varchar),
                    cast(:dailyChecksum as varchar), cast(:sourceAsOf as timestamptz),
                    cast(:continuity as varchar), cast(:runs as jsonb),
                    cast(:buckets as jsonb), cast(:idempotencyKey as varchar),
                    cast(:requestDigest as varchar))
                """)
                .param("rebuildId", publication.rebuildId())
                .param("windowStart", offset(publication.windowStart()))
                .param("windowEnd", offset(publication.windowEnd()))
                .param("expectedGeneration", publication.expectedGeneration())
                .param("eventCount", publication.journal().eventCount())
                .param("factCount", publication.hourly().factCount())
                .param("journalChecksum", publication.journal().checksum())
                .param("hourlyChecksum", publication.hourly().checksum())
                .param("dailyChecksum", publication.daily().checksum())
                .param("sourceAsOf", offset(sourceAsOf))
                .param("continuity", publication.journal().inputContinuity().name())
                .param("runs", writeJson(runs))
                .param("buckets", writeJson(buckets))
                .param("idempotencyKey", publication.idempotencyKey())
                .param("requestDigest", publication.requestDigest())
                .query(Long.class).single()));
    }

    @Override
    public Optional<ProjectionSnapshot> currentProjection(
            TaskFinopsPort.AuthenticatedContext context,
            TaskFinopsAnalytics.Grain grain,
            Instant from,
            Instant to,
            int limit
    ) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(grain, "grain");
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        if (!to.isAfter(from) || limit < 1 || limit > 10_000) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_ANALYTICS_QUERY_INVALID");
        }
        return inContext(context, () -> {
            Optional<Map<String, Object>> head = jdbc.sql("""
                    select rebuild.rebuild_id, rebuild.generation_version,
                           rebuild.source_as_of, rebuild.input_continuity,
                           rebuild.external_evidence_state,
                           rebuild.provider_outcome,
                           rebuild.production_certification,
                           rebuild.hourly_checksum, rebuild.daily_checksum
                      from task_finops_projection_heads head
                      join task_finops_projection_rebuilds rebuild
                        on rebuild.rebuild_id = head.rebuild_id
                       and rebuild.organization_id = head.organization_id
                       and rebuild.account_id = head.account_id
                       and rebuild.generation_version = head.generation_version
                     where head.organization_id = :organization
                       and head.account_id = :account
                    """)
                    .param("organization", context.organizationId())
                    .param("account", context.accountId())
                    .query((rs, row) -> Map.<String, Object>of(
                            "rebuildId", rs.getString("rebuild_id"),
                            "generation", rs.getLong("generation_version"),
                            "sourceAsOf", instant(rs, "source_as_of"),
                            "inputContinuity", rs.getString("input_continuity"),
                            "externalEvidence", rs.getString("external_evidence_state"),
                            "providerOutcome", rs.getString("provider_outcome"),
                            "productionCertification",
                            rs.getString("production_certification"),
                            "hourlyChecksum", rs.getString("hourly_checksum"),
                            "dailyChecksum", rs.getString("daily_checksum")))
                    .optional();
            if (head.isEmpty()) return Optional.empty();
            String rebuildId = (String) head.get().get("rebuildId");
            List<TaskFinopsAnalytics.AggregateBucket> rows = jdbc.sql("""
                    select organization_id, account_id, task_id, run_number,
                           workload_class, grain, bucket_start, bucket_end,
                           currency, allocation_basis, cost_delta_minor,
                           revenue_delta_minor, gross_delta_minor, fact_count,
                           completeness, reconciliation_status
                      from task_finops_aggregate_buckets
                     where rebuild_id = :rebuildId
                       and organization_id = :organization
                       and account_id = :account
                       and grain = :grain
                       and bucket_start >= cast(:windowStart as timestamptz)
                       and bucket_start < cast(:windowEnd as timestamptz)
                     order by bucket_start, task_id, run_number, workload_class,
                              currency, allocation_basis
                     limit :limit
                    """)
                    .param("rebuildId", rebuildId)
                    .param("organization", context.organizationId())
                    .param("account", context.accountId())
                    .param("grain", grain.name())
                    .param("windowStart", offset(from))
                    .param("windowEnd", offset(to))
                    .param("limit", limit + 1)
                    .query(this::readBucket)
                    .list();
            rows = bounded(rows, limit);
            return Optional.of(new ProjectionSnapshot(
                    rebuildId, (Long) head.get().get("generation"),
                    (Instant) head.get().get("sourceAsOf"),
                    enumValue(TaskFinopsAnalytics.InputContinuity.class,
                            (String) head.get().get("inputContinuity"),
                            "INPUT_CONTINUITY"),
                    enumValue(TaskFinopsAnalytics.ExternalEvidenceState.class,
                            (String) head.get().get("externalEvidence"),
                            "EXTERNAL_EVIDENCE"),
                    enumValue(TaskFinopsAnalytics.ProviderOutcome.class,
                            (String) head.get().get("providerOutcome"),
                            "PROVIDER_OUTCOME"),
                    enumValue(TaskFinopsAnalytics.ProductionCertification.class,
                            (String) head.get().get("productionCertification"),
                            "PRODUCTION_CERTIFICATION"),
                    (String) head.get().get("hourlyChecksum"),
                    (String) head.get().get("dailyChecksum"), rows));
        });
    }

    private LifecycleStatus readLifecycleStatus(ResultSet rs, int row) throws SQLException {
        return new LifecycleStatus(
                rs.getString("lifecycle_job_id"), rs.getString("organization_id"),
                rs.getString("account_id"),
                enumValue(TenantLifecyclePolicy.Operation.class,
                        rs.getString("operation_kind"), "LIFECYCLE_OPERATION"),
                enumValue(TenantLifecyclePolicy.ExportFormat.class,
                        rs.getString("export_format"), "EXPORT_FORMAT"),
                rs.getString("operation_state"), instant(rs, "retention_cutoff"),
                rs.getString("page_cursor"), rs.getString("manifest_digest"),
                rs.getLong("exported_row_count"), rs.getLong("exported_byte_count"),
                enumValue(TenantLifecyclePolicy.ProviderResult.class,
                        rs.getString("provider_result_state"), "PROVIDER_RESULT"),
                rs.getString("failure_code"), rs.getLong("state_version"),
                instant(rs, "requested_at"), instantOrNull(rs, "completed_at"));
    }

    private TaskFinopsAnalytics.AggregateBucket readBucket(ResultSet rs, int row)
            throws SQLException {
        return new TaskFinopsAnalytics.AggregateBucket(
                rs.getString("organization_id"), rs.getString("account_id"),
                rs.getString("task_id"), rs.getLong("run_number"),
                enumValue(TaskFinopsPolicy.WorkloadClass.class,
                        rs.getString("workload_class"), "WORKLOAD_CLASS"),
                enumValue(TaskFinopsAnalytics.Grain.class,
                        rs.getString("grain"), "GRAIN"),
                instant(rs, "bucket_start"), instant(rs, "bucket_end"),
                rs.getString("currency"),
                enumValue(TaskFinopsPort.AllocationBasis.class,
                        rs.getString("allocation_basis"), "ALLOCATION_BASIS"),
                rs.getBigDecimal("cost_delta_minor"),
                rs.getBigDecimal("revenue_delta_minor"),
                rs.getBigDecimal("gross_delta_minor"), rs.getLong("fact_count"),
                enumValue(TaskFinopsAnalytics.DataCompleteness.class,
                        rs.getString("completeness"), "COMPLETENESS"),
                enumValue(TaskFinopsPort.ReconciliationStatus.class,
                        rs.getString("reconciliation_status"),
                        "RECONCILIATION_STATUS"));
    }

    private Map<String, Object> runJson(TaskFinopsAnalytics.RunProjection row) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("organization_id", row.organizationId());
        value.put("account_id", row.accountId());
        value.put("task_id", row.taskId());
        value.put("run_number", row.runNumber());
        value.put("task_state", row.taskState().name());
        value.put("progress_percent", row.progressPercent());
        value.put("last_event_sequence", row.lastEventSequence());
        value.put("last_occurred_at", row.lastOccurredAt().toString());
        value.put("checksum", row.checksum());
        return value;
    }

    private static Map<String, Object> bucketJson(TaskFinopsAnalytics.AggregateBucket row) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("organization_id", row.organizationId());
        value.put("account_id", row.accountId());
        value.put("task_id", row.taskId());
        value.put("run_number", row.runNumber());
        value.put("workload_class", row.workloadClass().name());
        value.put("grain", row.grain().name());
        value.put("bucket_start", row.bucketStart().toString());
        value.put("bucket_end", row.bucketEnd().toString());
        value.put("currency", row.currency());
        value.put("allocation_basis", row.allocationBasis().name());
        value.put("cost_delta_minor", row.costDeltaMinor());
        value.put("revenue_delta_minor", row.revenueDeltaMinor());
        value.put("gross_delta_minor", row.grossDeltaMinor());
        value.put("fact_count", row.factCount());
        value.put("completeness", row.completeness().name());
        value.put("reconciliation_status", row.reconciliationStatus().name());
        return value;
    }

    private String writeJson(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_ANALYTICS_SERIALIZATION_FAILED");
        }
    }

    private <T> T inContext(
            TaskFinopsPort.AuthenticatedContext context,
            Supplier<T> work
    ) {
        return executeInContext(transactions, context, work);
    }

    private <T> T inAnalyticsContext(
            TaskFinopsPort.AuthenticatedContext context,
            Supplier<T> work
    ) {
        return executeInContext(analyticsTransactions, context, work);
    }

    private <T> T executeInContext(
            TransactionTemplate template,
            TaskFinopsPort.AuthenticatedContext context,
            Supplier<T> work
    ) {
        return template.execute(status -> domain(() -> {
            jdbc.sql("""
                    select elmos_mtf_bind_identity(
                        cast(:organization as varchar), cast(:account as varchar),
                        cast(:actor as varchar), cast(:request as varchar))
                    """)
                    .param("organization", context.organizationId())
                    .param("account", context.accountId())
                    .param("actor", context.actorId())
                    .param("request", context.requestId())
                    .query().singleRow();
            return work.get();
        }));
    }

    private static <T> List<T> bounded(List<T> rows, int limit) {
        if (rows.size() > limit) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_ANALYTICS_SOURCE_LIMIT_EXCEEDED");
        }
        return List.copyOf(rows);
    }

    private static Instant max(Instant left, Instant right) {
        return left.isAfter(right) ? left : right;
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Instant value = instantOrNull(rs, column);
        if (value == null) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_TIMESTAMP_MISSING");
        }
        return value;
    }

    private static Instant instantOrNull(ResultSet rs, String column) throws SQLException {
        OffsetDateTime value = rs.getObject(column, OffsetDateTime.class);
        return value == null ? null : value.toInstant();
    }

    private static PaymentSettlementReconciler.ReconciliationStatus settlementStatus(
            String value
    ) {
        return switch (value == null ? "" : value.toUpperCase(Locale.ROOT)) {
            case "MATCHED" -> PaymentSettlementReconciler.ReconciliationStatus.RECONCILED;
            case "UNRECONCILED" ->
                    PaymentSettlementReconciler.ReconciliationStatus.UNRECONCILED;
            case "UNKNOWN" -> PaymentSettlementReconciler.ReconciliationStatus.UNKNOWN;
            default -> throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_SETTLEMENT_STATE_INVALID");
        };
    }

    private static void requireSettlementParity(
            SettlementReceipt receipt,
            PaymentSettlementReconciler.ReconciliationRequest request,
            PaymentSettlementReconciler.ReconciliationResult expected,
            java.math.BigDecimal providerNet
    ) {
        java.math.BigDecimal ledgerNet =
                request.ledgerSettlement().amounts().netMinor();
        java.math.BigDecimal expectedDifference = providerNet == null
                ? null : providerNet.subtract(ledgerNet);
        if (!receipt.reconciliationId().equals(request.reconciliationId())
                || receipt.status() != expected.status()
                || !receipt.currency().equals(request.ledgerSettlement().currency())
                || !receipt.periodStart().equals(
                        request.ledgerSettlement().period().startInclusive())
                || !receipt.periodEnd().equals(
                        request.ledgerSettlement().period().endExclusive())
                || !sameDecimal(receipt.providerReportedMinor(), providerNet)
                || !sameDecimal(receipt.ledgerRecordedMinor(), ledgerNet)
                || !sameDecimal(receipt.differenceMinor(), expectedDifference)) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_SETTLEMENT_PARITY_MISMATCH");
        }
    }

    private static boolean sameDecimal(
            java.math.BigDecimal left,
            java.math.BigDecimal right
    ) {
        return left == null ? right == null
                : right != null && left.compareTo(right) == 0;
    }

    private static <T extends Enum<T>> T enumValue(
            Class<T> type,
            String value,
            String field
    ) {
        try {
            return Enum.valueOf(type,
                    value == null ? "" : value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_" + field + "_INVALID");
        }
    }

    private static <T> T domain(Supplier<T> work) {
        try {
            return work.get();
        } catch (TaskFinopsPort.TaskFinopsStateException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            String message = rootMessage(exception);
            int marker = message == null ? -1 : message.indexOf("ELMOS_MTF_");
            if (marker >= 0) {
                String tail = message.substring(marker);
                int end = 0;
                while (end < tail.length()) {
                    char value = tail.charAt(end);
                    if (!(value == '_' || value >= 'A' && value <= 'Z'
                            || value >= '0' && value <= '9')) break;
                    end++;
                }
                throw new TaskFinopsPort.TaskFinopsStateException(
                        end > 0 ? tail.substring(0, end)
                                : "ELMOS_MTF_PERSISTENCE_FAILURE");
            }
            throw exception;
        }
    }

    private static String rootMessage(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current.getMessage();
    }

    private static void require(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 96) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_" + field + "_INVALID");
        }
    }
}
