package io.elmos.persistence;

import static io.elmos.persistence.SqlTimestamps.offset;

import io.elmos.workflow.TaskFinopsPolicy;
import io.elmos.workflow.TaskFinopsPort;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;

/**
 * PostgreSQL adapter for the repository-owned multi-tenant task/FinOps schema.
 *
 * <p>Identity is transaction-local and is bound before every read or write.
 * Reads additionally constrain both organization and account; this is deliberate
 * defense in depth over V77's forced RLS policies.  Mutations only use the
 * repository-owned {@code elmos_mtf_*} functions, which own idempotency, locking,
 * append-only journal rules, and segregation-of-duties checks.</p>
 */
public final class JdbcTaskFinopsStore implements TaskFinopsPort {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcTaskFinopsStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public ConcurrencyStatus concurrencyStatus(AuthenticatedContext context) {
        Objects.requireNonNull(context, "context");
        return inContext(context, () -> jdbc.sql("""
                select organization_id, account_id, root_task_limit,
                       active_root_tasks, waiting_root_tasks, available_root_slots,
                       as_of, reconciliation_status
                  from mtf_account_concurrency_status
                 where organization_id = :organization
                   and account_id = :account
                """)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .query((rs, row) -> new ConcurrencyStatus(
                        rs.getString("organization_id"),
                        rs.getString("account_id"),
                        rs.getInt("root_task_limit"),
                        rs.getInt("active_root_tasks"),
                        rs.getInt("waiting_root_tasks"),
                        rs.getInt("available_root_slots"),
                        instant(rs, "as_of"),
                        reconciliation(rs.getString("reconciliation_status"))))
                .optional()
                .orElseThrow(() -> new TaskFinopsStateException(
                        "ELMOS_MTF_ACCOUNT_CONTEXT_UNKNOWN")));
    }

    @Override
    public List<TaskEvent> events(
            AuthenticatedContext context,
            String taskId,
            long afterSequence,
            int limit
    ) {
        Objects.requireNonNull(context, "context");
        requireIdentifier(taskId, "TASK");
        if (afterSequence < 0) {
            throw new TaskFinopsStateException("ELMOS_MTF_EVENT_CURSOR_INVALID");
        }
        int boundedLimit = Math.min(Math.max(limit, 1), 500);
        return inContext(context, () -> jdbc.sql("""
                select organization_id, account_id, task_id, event_id,
                       event_sequence, event_type, task_state, stage,
                       progress_percent, actor_id, occurred_at, evidence_digest
                  from mtf_task_events
                 where organization_id = :organization
                   and account_id = :account
                   and task_id = :task
                   and event_sequence > :afterSequence
                 order by event_sequence asc, event_id asc
                 limit :limit
                """)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .param("task", taskId)
                .param("afterSequence", afterSequence)
                .param("limit", boundedLimit)
                .query(this::readEvent)
                .list());
    }

    @Override
    public Optional<ProgressSnapshot> progress(
            AuthenticatedContext context,
            String taskId
    ) {
        Objects.requireNonNull(context, "context");
        requireIdentifier(taskId, "TASK");
        return inContext(context, () -> jdbc.sql("""
                select organization_id, account_id, task_id, task_state, stage,
                       progress_percent, elapsed_millis, eta_p50_millis,
                       eta_p90_millis, last_event_sequence, as_of,
                       reconciliation_status
                  from mtf_task_progress
                 where organization_id = :organization
                   and account_id = :account
                   and task_id = :task
                """)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .param("task", taskId)
                .query((rs, row) -> new ProgressSnapshot(
                        rs.getString("organization_id"),
                        rs.getString("account_id"),
                        rs.getString("task_id"),
                        taskState(rs.getString("task_state")),
                        rs.getString("stage"),
                        rs.getShort("progress_percent"),
                        rs.getLong("elapsed_millis"),
                        rs.getLong("eta_p50_millis"),
                        rs.getLong("eta_p90_millis"),
                        rs.getLong("last_event_sequence"),
                        instant(rs, "as_of"),
                        reconciliation(rs.getString("reconciliation_status"))))
                .optional());
    }

    @Override
    public Optional<FinancialSummary> financialSummary(
            AuthenticatedContext context,
            String taskId,
            Instant asOf
    ) {
        Objects.requireNonNull(context, "context");
        requireIdentifier(taskId, "TASK");
        Objects.requireNonNull(asOf, "asOf");
        return inContext(context, () -> jdbc.sql("""
                select organization_id, account_id, task_id, currency,
                       estimated_cost_minor, reserved_cost_minor, posted_cost_minor,
                       final_cost_minor, recognized_revenue_minor,
                       collected_cash_minor, refunds_minor, gross_profit_minor,
                       gross_margin_ratio, usage_entry_count,
                       unreconciled_usage_count, revenue_entry_count,
                       unreconciled_revenue_count, event_watermark, as_of,
                       reconciliation_status, qualification
                  from mtf_task_financial_summary
                 where organization_id = :organization
                   and account_id = :account
                   and task_id = :task
                   and as_of <= cast(:asOf as timestamptz)
                 order by as_of desc
                 limit 1
                """)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .param("task", taskId)
                .param("asOf", offset(asOf))
                .query(this::readFinancialSummary)
                .optional());
    }

    @Override
    public String appendCheckpoint(Checkpoint checkpoint) {
        Objects.requireNonNull(checkpoint, "checkpoint");
        return inContext(checkpoint.context(), () -> mapDomainErrors(() -> jdbc.sql("""
                select elmos_mtf_append_checkpoint(
                    cast(:checkpointId as varchar), cast(:taskId as varchar),
                    cast(:runId as varchar), cast(:nodeId as varchar),
                    cast(:checkpointSequence as bigint),
                    cast(:inputManifestDigest as varchar),
                    cast(:repositoryRevision as varchar),
                    cast(:toolchainDigest as varchar), cast(:modelDigest as varchar),
                    cast(:schemaVersion as varchar), cast(:objectRef as varchar),
                    cast(:contentDigest as varchar), cast(:contentLength as bigint),
                    cast(:createdAt as timestamptz), cast(:idempotencyKey as varchar))
                """)
                .param("checkpointId", checkpoint.checkpointId())
                .param("taskId", checkpoint.taskId())
                .param("runId", checkpoint.runId())
                .param("nodeId", checkpoint.nodeId())
                .param("checkpointSequence", checkpoint.checkpointSequence())
                .param("inputManifestDigest", checkpoint.inputManifestDigest())
                .param("repositoryRevision", checkpoint.repositoryRevision())
                .param("toolchainDigest", checkpoint.toolchainDigest())
                .param("modelDigest", checkpoint.modelDigest())
                .param("schemaVersion", checkpoint.schemaVersion())
                .param("objectRef", checkpoint.objectRef())
                .param("contentDigest", checkpoint.contentDigest())
                .param("contentLength", checkpoint.contentLength())
                .param("createdAt", offset(checkpoint.createdAt()))
                .param("idempotencyKey", checkpoint.idempotencyKey())
                .query(String.class).single()));
    }

    @Override
    public String recordSideEffectReceipt(SideEffectReceipt receipt) {
        Objects.requireNonNull(receipt, "receipt");
        return inContext(receipt.context(), () -> mapDomainErrors(() -> jdbc.sql("""
                select elmos_mtf_record_side_effect_receipt(
                    cast(:receiptId as varchar), cast(:taskId as varchar),
                    cast(:runId as varchar), cast(:nodeId as varchar),
                    cast(:effectType as varchar), cast(:idempotencyKey as varchar),
                    cast(:requestDigest as varchar), cast(:resultDigest as varchar),
                    cast(:providerReference as varchar), cast(:resultState as varchar),
                    cast(:occurredAt as timestamptz),
                    cast(:signatureAlgorithm as varchar), cast(:signingKeyId as varchar),
                    cast(:signature as varchar))
                """)
                .param("receiptId", receipt.receiptId())
                .param("taskId", receipt.taskId())
                .param("runId", receipt.runId())
                .param("nodeId", receipt.nodeId())
                .param("effectType", receipt.effectType())
                .param("idempotencyKey", receipt.idempotencyKey())
                .param("requestDigest", receipt.requestDigest())
                .param("resultDigest", receipt.resultDigest())
                .param("providerReference", receipt.providerReference())
                .param("resultState", receipt.resultState().name())
                .param("occurredAt", offset(receipt.occurredAt()))
                .param("signatureAlgorithm", receipt.signatureAlgorithm())
                .param("signingKeyId", receipt.signingKeyId())
                .param("signature", receipt.signature())
                .query(String.class).single()));
    }

    @Override
    public String recordUsage(UsageEntry entry) {
        Objects.requireNonNull(entry, "entry");
        return inContext(entry.context(), () -> mapDomainErrors(() -> jdbc.sql("""
                select elmos_mtf_record_usage(
                    cast(:usageEntryId as varchar), cast(:taskId as varchar),
                    cast(:runId as varchar), cast(:provider as varchar),
                    cast(:providerSku as varchar), cast(:usageUnit as varchar),
                    cast(:quantity as numeric), cast(:priceBookId as varchar),
                    cast(:priceBookVersion as varchar),
                    cast(:priceEffectiveAt as timestamptz),
                    cast(:sourceCurrency as varchar), cast(:unitPriceMinor as numeric),
                    cast(:fxSnapshotId as varchar), cast(:baseCurrency as varchar),
                    cast(:fxRate as numeric), cast(:sourceCostMinor as numeric),
                    cast(:baseCostMinor as numeric), cast(:costState as varchar),
                    cast(:reconciliationStatus as varchar),
                    cast(:providerReceiptRef as varchar),
                    cast(:periodStart as timestamptz), cast(:periodEnd as timestamptz),
                    cast(:occurredAt as timestamptz), cast(:idempotencyKey as varchar),
                    cast(:correctionOfUsageEntryId as varchar))
                """)
                .param("usageEntryId", entry.usageEntryId())
                .param("taskId", entry.taskId())
                .param("runId", entry.runId())
                .param("provider", entry.provider())
                .param("providerSku", entry.providerSku())
                .param("usageUnit", entry.usageUnit())
                .param("quantity", entry.quantity())
                .param("priceBookId", entry.priceBookId())
                .param("priceBookVersion", entry.priceBookVersion())
                .param("priceEffectiveAt", offset(entry.priceEffectiveAt()))
                .param("sourceCurrency", entry.sourceCurrency())
                .param("unitPriceMinor", entry.unitPriceMinor())
                .param("fxSnapshotId", entry.fxSnapshotId())
                .param("baseCurrency", entry.baseCurrency())
                .param("fxRate", entry.fxRate())
                .param("sourceCostMinor", entry.sourceCostMinor())
                .param("baseCostMinor", entry.baseCostMinor())
                .param("costState", entry.costState().name())
                .param("reconciliationStatus", entry.reconciliationStatus().name())
                .param("providerReceiptRef", entry.providerReceiptRef())
                .param("periodStart", offset(entry.periodStart()))
                .param("periodEnd", offset(entry.periodEnd()))
                .param("occurredAt", offset(entry.occurredAt()))
                .param("idempotencyKey", entry.idempotencyKey())
                .param("correctionOfUsageEntryId", entry.correctionOfUsageEntryId())
                .query(String.class).single()));
    }

    @Override
    public String recordRevenue(RevenueEntry entry) {
        Objects.requireNonNull(entry, "entry");
        return inContext(entry.context(), () -> mapDomainErrors(() -> jdbc.sql("""
                select elmos_mtf_record_revenue(
                    cast(:revenueEntryId as varchar), cast(:taskId as varchar),
                    cast(:projectId as varchar), cast(:legalEntityId as varchar),
                    cast(:entryKind as varchar), cast(:entryState as varchar),
                    cast(:currency as varchar), cast(:amountMinor as numeric),
                    cast(:effectiveAt as timestamptz), cast(:periodStart as timestamptz),
                    cast(:periodEnd as timestamptz), cast(:sourceType as varchar),
                    cast(:sourceReference as varchar),
                    cast(:correctionOfRevenueEntryId as varchar),
                    cast(:reconciliationStatus as varchar),
                    cast(:signatureAlgorithm as varchar), cast(:signingKeyId as varchar),
                    cast(:signedDigest as varchar), cast(:signature as varchar),
                    cast(:idempotencyKey as varchar))
                """)
                .param("revenueEntryId", entry.revenueEntryId())
                .param("taskId", entry.taskId())
                .param("projectId", entry.projectId())
                .param("legalEntityId", entry.legalEntityId())
                .param("entryKind", entry.entryKind().name())
                .param("entryState", entry.entryState().name())
                .param("currency", entry.currency())
                .param("amountMinor", entry.amountMinor())
                .param("effectiveAt", offset(entry.effectiveAt()))
                .param("periodStart", offset(entry.periodStart()))
                .param("periodEnd", offset(entry.periodEnd()))
                .param("sourceType", entry.sourceType())
                .param("sourceReference", entry.sourceReference())
                .param("correctionOfRevenueEntryId", entry.correctionOfRevenueEntryId())
                .param("reconciliationStatus", entry.reconciliationStatus().name())
                .param("signatureAlgorithm", entry.signatureAlgorithm())
                .param("signingKeyId", entry.signingKeyId())
                .param("signedDigest", entry.signedDigest())
                .param("signature", entry.signature())
                .param("idempotencyKey", entry.idempotencyKey())
                .query(String.class).single()));
    }

    @Override
    public String allocateRevenue(RevenueAllocation allocation) {
        Objects.requireNonNull(allocation, "allocation");
        return inContext(allocation.context(), () -> mapDomainErrors(() -> jdbc.sql("""
                select elmos_mtf_allocate_revenue(
                    cast(:allocationId as varchar), cast(:revenueEntryId as varchar),
                    cast(:taskId as varchar), cast(:projectId as varchar),
                    cast(:allocationBasis as varchar), cast(:policyVersion as varchar),
                    cast(:currency as varchar), cast(:amountMinor as numeric),
                    cast(:effectiveAt as timestamptz),
                    cast(:signatureAlgorithm as varchar), cast(:signingKeyId as varchar),
                    cast(:signedDigest as varchar), cast(:signature as varchar),
                    cast(:idempotencyKey as varchar))
                """)
                .param("allocationId", allocation.allocationId())
                .param("revenueEntryId", allocation.revenueEntryId())
                .param("taskId", allocation.taskId())
                .param("projectId", allocation.projectId())
                .param("allocationBasis", allocation.allocationBasis().name())
                .param("policyVersion", allocation.policyVersion())
                .param("currency", allocation.currency())
                .param("amountMinor", allocation.amountMinor())
                .param("effectiveAt", offset(allocation.effectiveAt()))
                .param("signatureAlgorithm", allocation.signatureAlgorithm())
                .param("signingKeyId", allocation.signingKeyId())
                .param("signedDigest", allocation.signedDigest())
                .param("signature", allocation.signature())
                .param("idempotencyKey", allocation.idempotencyKey())
                .query(String.class).single()));
    }

    @Override
    public TaskFinopsPolicy.TaskState pause(ControlCommand command) {
        return control("elmos_mtf_pause_task", command);
    }

    @Override
    public TaskFinopsPolicy.TaskState resume(ControlCommand command) {
        return control("elmos_mtf_resume_task", command);
    }

    @Override
    public ReconciliationStatus requestManualReconciliation(
            ManualReconciliationCommand command
    ) {
        Objects.requireNonNull(command, "command");
        return inContext(command.context(), () -> mapDomainErrors(() -> reconciliation(
                jdbc.sql("""
                        select elmos_mtf_request_manual_reconciliation(
                            cast(:taskId as varchar), cast(:reasonCode as varchar),
                            cast(:evidenceReference as varchar),
                            cast(:idempotencyKey as varchar))
                        """)
                        .param("taskId", command.taskId())
                        .param("reasonCode", command.reasonCode())
                        .param("evidenceReference", command.evidenceReference())
                        .param("idempotencyKey", command.idempotencyKey())
                        .query(String.class).single())));
    }

    private TaskFinopsPolicy.TaskState control(
            String function,
            ControlCommand command
    ) {
        Objects.requireNonNull(command, "command");
        // Function is selected only by the two internal call sites above, never input.
        String sql = "select " + function + "(" +
                "cast(:taskId as varchar), cast(:reasonCode as varchar), " +
                "cast(:idempotencyKey as varchar), cast(:requestDigest as varchar))";
        return inContext(command.context(), () -> mapDomainErrors(() -> taskState(
                jdbc.sql(sql)
                        .param("taskId", command.taskId())
                        .param("reasonCode", command.reasonCode())
                        .param("idempotencyKey", command.idempotencyKey())
                        .param("requestDigest", command.requestDigest())
                        .query(String.class).single())));
    }

    private <T> T inContext(AuthenticatedContext context, Supplier<T> work) {
        return transactions.execute(status -> mapDomainErrors(() -> {
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

    private TaskEvent readEvent(ResultSet rs, int row) throws SQLException {
        return new TaskEvent(
                rs.getString("organization_id"),
                rs.getString("account_id"),
                rs.getString("task_id"),
                rs.getString("event_id"),
                rs.getLong("event_sequence"),
                rs.getString("event_type"),
                taskState(rs.getString("task_state")),
                rs.getString("stage"),
                rs.getShort("progress_percent"),
                rs.getString("actor_id"),
                instant(rs, "occurred_at"),
                rs.getString("evidence_digest"));
    }

    private FinancialSummary readFinancialSummary(ResultSet rs, int row) throws SQLException {
        return new FinancialSummary(
                rs.getString("organization_id"),
                rs.getString("account_id"),
                rs.getString("task_id"),
                rs.getString("currency"),
                rs.getBigDecimal("estimated_cost_minor"),
                rs.getBigDecimal("reserved_cost_minor"),
                rs.getBigDecimal("posted_cost_minor"),
                rs.getBigDecimal("final_cost_minor"),
                rs.getBigDecimal("recognized_revenue_minor"),
                rs.getBigDecimal("collected_cash_minor"),
                rs.getBigDecimal("refunds_minor"),
                rs.getBigDecimal("gross_profit_minor"),
                rs.getBigDecimal("gross_margin_ratio"),
                rs.getLong("usage_entry_count"),
                rs.getLong("unreconciled_usage_count"),
                rs.getLong("revenue_entry_count"),
                rs.getLong("unreconciled_revenue_count"),
                instantOrNull(rs, "event_watermark"),
                instant(rs, "as_of"),
                reconciliation(rs.getString("reconciliation_status")),
                enumValue(FinancialQualification.class,
                        rs.getString("qualification"), "FINANCIAL_QUALIFICATION"));
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Instant value = instantOrNull(rs, column);
        if (value == null) {
            throw new TaskFinopsStateException("ELMOS_MTF_TIMESTAMP_MISSING");
        }
        return value;
    }

    private static Instant instantOrNull(ResultSet rs, String column) throws SQLException {
        OffsetDateTime value = rs.getObject(column, OffsetDateTime.class);
        return value == null ? null : value.toInstant();
    }

    private static TaskFinopsPolicy.TaskState taskState(String value) {
        return enumValue(TaskFinopsPolicy.TaskState.class, value, "TASK_STATE");
    }

    private static ReconciliationStatus reconciliation(String value) {
        return enumValue(ReconciliationStatus.class, value, "RECONCILIATION_STATUS");
    }

    private static <T extends Enum<T>> T enumValue(
            Class<T> type,
            String value,
            String field
    ) {
        try {
            return Enum.valueOf(type, value == null ? "" : value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new TaskFinopsStateException("ELMOS_MTF_" + field + "_INVALID");
        }
    }

    private static <T> T mapDomainErrors(Supplier<T> work) {
        try {
            return work.get();
        } catch (TaskFinopsStateException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            String message = rootMessage(exception);
            int marker = message == null ? -1 : message.indexOf("ELMOS_MTF_");
            if (marker >= 0) {
                String tail = message.substring(marker);
                int end = tail.indexOf(' ');
                throw new TaskFinopsStateException(end > 0 ? tail.substring(0, end) : tail);
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

    private static void requireIdentifier(String value, String field) {
        if (value == null || value.isBlank()
                || value.length() > TaskFinopsPort.DATABASE_ID_MAX_LENGTH) {
            throw new TaskFinopsStateException("ELMOS_MTF_" + field + "_INVALID");
        }
    }
}
