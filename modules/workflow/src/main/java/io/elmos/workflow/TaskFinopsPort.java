package io.elmos.workflow;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;

/**
 * Tenant- and account-bound durable task economics contract.
 *
 * <p>This port deliberately extends the existing task, usage, and billing
 * aggregates instead of introducing another ledger.  All monetary and usage
 * values are exact decimals.  A reconciliation status is part of every
 * financial projection so an unknown provider, invoice, or cash result cannot
 * be presented as final.</p>
 *
 * <p>Public control-plane code may use the read methods plus {@link #pause} and
 * {@link #resume}.  Checkpoint, receipt, usage, revenue, allocation, and manual
 * reconciliation methods are internal workflow/finance adapter boundaries.</p>
 */
public interface TaskFinopsPort {
    int USAGE_SCALE = 9;
    int PROVIDER_PRICE_SCALE = 9;
    int FX_RATE_SCALE = 12;
    int DATABASE_ID_MAX_LENGTH = 96;
    int DATABASE_ACTOR_ID_MAX_LENGTH = 128;
    int DATABASE_DECIMAL_MAX_PRECISION = 30;

    enum CostState {
        ESTIMATED, RESERVED, POSTED, FINAL, REVERSED, DISPUTED, UNRECONCILED
    }

    enum ReconciliationStatus {
        PENDING, RECONCILED, REJECTED, UNKNOWN, INCONCLUSIVE
    }

    enum SideEffectState {
        CONFIRMED, FAILED, UNKNOWN
    }

    enum RevenueKind {
        CHARGE, CREDIT, REFUND, CASH_RECEIPT, REVENUE_RECOGNITION,
        TAX, PAYMENT_FEE, CORRECTION, REVERSAL
    }

    enum RevenueState {
        RECORDED, POSTED, RECOGNIZED, COLLECTED, REFUNDED,
        REVERSED, DISPUTED, UNRECONCILED
    }

    enum AllocationBasis {
        DIRECT_TASK, DIRECT_PROJECT, MILESTONE, USAGE,
        SUBSCRIPTION_POLICY, MANUAL_APPROVED
    }

    enum FinancialQualification {
        CURRENT, PARTIAL, STALE, UNRECONCILED
    }

    /** Stable failures only; database/provider text must not cross this boundary. */
    final class TaskFinopsStateException extends RuntimeException {
        private final String code;

        public TaskFinopsStateException(String code) {
            super(code);
            this.code = Objects.requireNonNull(code, "code");
        }

        public String code() {
            return code;
        }
    }

    /** Identity selected from authenticated membership, never from request payload fields. */
    record AuthenticatedContext(
            String organizationId,
            String accountId,
            String actorId,
            String requestId
    ) {
        public AuthenticatedContext {
            organizationId = identifier(
                    organizationId, "ORGANIZATION", DATABASE_ID_MAX_LENGTH);
            accountId = identifier(accountId, "ACCOUNT", DATABASE_ID_MAX_LENGTH);
            actorId = identifier(actorId, "ACTOR", DATABASE_ACTOR_ID_MAX_LENGTH);
            requestId = identifier(requestId, "REQUEST", 160);
        }
    }

    record ConcurrencyStatus(
            String organizationId,
            String accountId,
            int rootTaskLimit,
            int activeRootTasks,
            int waitingRootTasks,
            int availableRootSlots,
            Instant asOf,
            ReconciliationStatus reconciliationStatus
    ) {
        public ConcurrencyStatus {
            organizationId = identifier(
                    organizationId, "ORGANIZATION", DATABASE_ID_MAX_LENGTH);
            accountId = identifier(accountId, "ACCOUNT", DATABASE_ID_MAX_LENGTH);
            if (rootTaskLimit < 0
                    || rootTaskLimit > TaskFinopsPolicy.MAX_ACCOUNT_ROOT_TASKS
                    || activeRootTasks < 0
                    || waitingRootTasks < 0
                    || availableRootSlots < 0
                    || availableRootSlots > rootTaskLimit) {
                throw new IllegalArgumentException("ELMOS_MTF_CONCURRENCY_STATUS_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
        }
    }

    /** Immutable, gap-detectable event. Ordering is by {@code eventSequence}. */
    record TaskEvent(
            String organizationId,
            String accountId,
            String taskId,
            String eventId,
            long eventSequence,
            String eventType,
            TaskFinopsPolicy.TaskState taskState,
            String stage,
            short progressPercent,
            String actorId,
            Instant occurredAt,
            String evidenceDigest
    ) {
        public TaskEvent {
            organizationId = identifier(
                    organizationId, "ORGANIZATION", DATABASE_ID_MAX_LENGTH);
            accountId = identifier(accountId, "ACCOUNT", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            eventId = identifier(eventId, "EVENT", DATABASE_ID_MAX_LENGTH);
            eventType = identifier(eventType, "EVENT_TYPE", 48);
            actorId = identifier(actorId, "ACTOR", DATABASE_ACTOR_ID_MAX_LENGTH);
            if (eventSequence < 1 || progressPercent < 0 || progressPercent > 100) {
                throw new IllegalArgumentException("ELMOS_MTF_EVENT_INVALID");
            }
            Objects.requireNonNull(taskState, "taskState");
            stage = optional(stage, 64, "STAGE");
            Objects.requireNonNull(occurredAt, "occurredAt");
            evidenceDigest = optionalDigest(evidenceDigest, "EVENT_EVIDENCE");
        }
    }

    record ProgressSnapshot(
            String organizationId,
            String accountId,
            String taskId,
            TaskFinopsPolicy.TaskState taskState,
            String stage,
            short progressPercent,
            long elapsedMillis,
            long etaP50Millis,
            long etaP90Millis,
            long lastEventSequence,
            Instant asOf,
            ReconciliationStatus reconciliationStatus
    ) {
        public ProgressSnapshot {
            organizationId = identifier(
                    organizationId, "ORGANIZATION", DATABASE_ID_MAX_LENGTH);
            accountId = identifier(accountId, "ACCOUNT", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            Objects.requireNonNull(taskState, "taskState");
            stage = optional(stage, 64, "STAGE");
            if (progressPercent < 0 || progressPercent > 100 || elapsedMillis < 0
                    || etaP50Millis < 0 || etaP90Millis < etaP50Millis
                    || lastEventSequence < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_SNAPSHOT_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
        }
    }

    record Checkpoint(
            AuthenticatedContext context,
            String checkpointId,
            String taskId,
            String runId,
            String nodeId,
            long checkpointSequence,
            String inputManifestDigest,
            String repositoryRevision,
            String toolchainDigest,
            String modelDigest,
            String schemaVersion,
            String objectRef,
            String contentDigest,
            long contentLength,
            Instant createdAt,
            String idempotencyKey
    ) {
        public Checkpoint {
            Objects.requireNonNull(context, "context");
            checkpointId = identifier(
                    checkpointId, "CHECKPOINT", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            runId = runIdentifier(runId);
            nodeId = identifier(nodeId, "NODE", DATABASE_ID_MAX_LENGTH);
            if (checkpointSequence < 1 || contentLength < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_CHECKPOINT_INVALID");
            }
            inputManifestDigest = digest(inputManifestDigest, "INPUT_MANIFEST");
            repositoryRevision = identifier(repositoryRevision, "REVISION", 160);
            toolchainDigest = digest(toolchainDigest, "TOOLCHAIN");
            modelDigest = optionalDigest(modelDigest, "MODEL");
            schemaVersion = identifier(schemaVersion, "SCHEMA_VERSION", 64);
            objectRef = identifier(objectRef, "OBJECT_REF", 512);
            contentDigest = digest(contentDigest, "CONTENT");
            Objects.requireNonNull(createdAt, "createdAt");
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
        }
    }

    /** Append-only proof of an attempted external or otherwise irreversible effect. */
    record SideEffectReceipt(
            AuthenticatedContext context,
            String receiptId,
            String taskId,
            String runId,
            String nodeId,
            String effectType,
            String idempotencyKey,
            String requestDigest,
            String resultDigest,
            String providerReference,
            SideEffectState resultState,
            Instant occurredAt,
            String signatureAlgorithm,
            String signingKeyId,
            String signature
    ) {
        public SideEffectReceipt {
            Objects.requireNonNull(context, "context");
            receiptId = identifier(receiptId, "RECEIPT", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            runId = runIdentifier(runId);
            nodeId = identifier(nodeId, "NODE", DATABASE_ID_MAX_LENGTH);
            effectType = identifier(effectType, "EFFECT_TYPE", 48);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "EFFECT_REQUEST");
            resultDigest = digest(resultDigest, "EFFECT_RESULT");
            providerReference = optional(providerReference, 255, "PROVIDER_REFERENCE");
            Objects.requireNonNull(resultState, "resultState");
            Objects.requireNonNull(occurredAt, "occurredAt");
            signatureAlgorithm = identifier(signatureAlgorithm, "SIGNATURE_ALGORITHM", 64);
            signingKeyId = identifier(signingKeyId, "SIGNING_KEY", 255);
            signature = identifier(signature, "SIGNATURE", 4096);
        }
    }

    record UsageEntry(
            AuthenticatedContext context,
            String usageEntryId,
            String taskId,
            String runId,
            String provider,
            String providerSku,
            String usageUnit,
            BigDecimal quantity,
            String priceBookId,
            String priceBookVersion,
            Instant priceEffectiveAt,
            String sourceCurrency,
            BigDecimal unitPriceMinor,
            String fxSnapshotId,
            String baseCurrency,
            BigDecimal fxRate,
            BigDecimal sourceCostMinor,
            BigDecimal baseCostMinor,
            CostState costState,
            ReconciliationStatus reconciliationStatus,
            String providerReceiptRef,
            Instant periodStart,
            Instant periodEnd,
            Instant occurredAt,
            String idempotencyKey,
            String correctionOfUsageEntryId
    ) {
        public UsageEntry {
            Objects.requireNonNull(context, "context");
            usageEntryId = identifier(
                    usageEntryId, "USAGE_ENTRY", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            runId = runIdentifier(runId);
            provider = identifier(provider, "PROVIDER", 64);
            providerSku = identifier(providerSku, "PROVIDER_SKU", 128);
            usageUnit = identifier(usageUnit, "USAGE_UNIT", 32);
            quantity = positiveDecimal(quantity, USAGE_SCALE, "QUANTITY");
            priceBookId = identifier(priceBookId, "PRICE_BOOK", DATABASE_ID_MAX_LENGTH);
            priceBookVersion = identifier(priceBookVersion, "PRICE_BOOK_VERSION", 96);
            Objects.requireNonNull(priceEffectiveAt, "priceEffectiveAt");
            sourceCurrency = currency(sourceCurrency);
            unitPriceMinor = nonNegativeDecimal(
                    unitPriceMinor, PROVIDER_PRICE_SCALE, "UNIT_PRICE");
            fxSnapshotId = identifier(
                    fxSnapshotId, "FX_SNAPSHOT", DATABASE_ID_MAX_LENGTH);
            baseCurrency = currency(baseCurrency);
            fxRate = positiveDecimal(fxRate, FX_RATE_SCALE, "FX_RATE");
            sourceCostMinor = nonNegativeDecimal(
                    sourceCostMinor, TaskFinopsPolicy.MONEY_SCALE, "SOURCE_COST");
            baseCostMinor = nonNegativeDecimal(baseCostMinor,
                    TaskFinopsPolicy.MONEY_SCALE, "BASE_COST");
            Objects.requireNonNull(costState, "costState");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
            if (costState == CostState.FINAL
                    && reconciliationStatus != ReconciliationStatus.RECONCILED) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_FINAL_COST_RECONCILIATION_REQUIRED");
            }
            providerReceiptRef = optional(providerReceiptRef, 255, "PROVIDER_RECEIPT");
            requireWindow(periodStart, periodEnd);
            Objects.requireNonNull(occurredAt, "occurredAt");
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            correctionOfUsageEntryId = optional(
                    correctionOfUsageEntryId, DATABASE_ID_MAX_LENGTH,
                    "CORRECTION_USAGE_ENTRY");
        }
    }

    /** Signed, immutable revenue/cash/refund/correction fact. Amount is signed. */
    record RevenueEntry(
            AuthenticatedContext context,
            String revenueEntryId,
            String taskId,
            String projectId,
            String legalEntityId,
            RevenueKind entryKind,
            RevenueState entryState,
            String currency,
            BigDecimal amountMinor,
            Instant effectiveAt,
            Instant periodStart,
            Instant periodEnd,
            String sourceType,
            String sourceReference,
            String correctionOfRevenueEntryId,
            ReconciliationStatus reconciliationStatus,
            String signatureAlgorithm,
            String signingKeyId,
            String signedDigest,
            String signature,
            String idempotencyKey
    ) {
        public RevenueEntry {
            Objects.requireNonNull(context, "context");
            revenueEntryId = identifier(
                    revenueEntryId, "REVENUE_ENTRY", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            projectId = optional(projectId, DATABASE_ID_MAX_LENGTH, "PROJECT");
            legalEntityId = identifier(
                    legalEntityId, "LEGAL_ENTITY", DATABASE_ID_MAX_LENGTH);
            Objects.requireNonNull(entryKind, "entryKind");
            Objects.requireNonNull(entryState, "entryState");
            currency = TaskFinopsPort.currency(currency);
            amountMinor = nonZeroSignedMoney(amountMinor, "REVENUE_AMOUNT");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            requireWindow(periodStart, periodEnd);
            sourceType = identifier(sourceType, "REVENUE_SOURCE_TYPE", 96);
            sourceReference = identifier(sourceReference, "REVENUE_SOURCE_REFERENCE", 512);
            correctionOfRevenueEntryId = optional(
                    correctionOfRevenueEntryId, DATABASE_ID_MAX_LENGTH,
                    "CORRECTION_REVENUE_ENTRY");
            requireRevenueSemantics(
                    entryKind, entryState, amountMinor, correctionOfRevenueEntryId);
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
            signatureAlgorithm = identifier(signatureAlgorithm, "SIGNATURE_ALGORITHM", 64);
            signingKeyId = identifier(signingKeyId, "SIGNING_KEY", 255);
            signedDigest = digest(signedDigest, "SIGNED_REVENUE");
            signature = identifier(signature, "SIGNATURE", 4096);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
        }
    }

    /**
     * Signed allocation. V77 rejects over-allocation; a partial allocation is
     * retained as an unreconciled financial-summary item until conservation is
     * complete.
     */
    record RevenueAllocation(
            AuthenticatedContext context,
            String allocationId,
            String revenueEntryId,
            String taskId,
            String projectId,
            AllocationBasis allocationBasis,
            String policyVersion,
            String currency,
            BigDecimal amountMinor,
            Instant effectiveAt,
            String signatureAlgorithm,
            String signingKeyId,
            String signedDigest,
            String signature,
            String idempotencyKey
    ) {
        public RevenueAllocation {
            Objects.requireNonNull(context, "context");
            allocationId = identifier(
                    allocationId, "ALLOCATION", DATABASE_ID_MAX_LENGTH);
            revenueEntryId = identifier(
                    revenueEntryId, "REVENUE_ENTRY", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            projectId = optional(projectId, DATABASE_ID_MAX_LENGTH, "PROJECT");
            Objects.requireNonNull(allocationBasis, "allocationBasis");
            policyVersion = identifier(policyVersion, "ALLOCATION_POLICY", 64);
            currency = TaskFinopsPort.currency(currency);
            amountMinor = nonZeroSignedMoney(amountMinor, "ALLOCATION_AMOUNT");
            Objects.requireNonNull(effectiveAt, "effectiveAt");
            signatureAlgorithm = identifier(signatureAlgorithm, "SIGNATURE_ALGORITHM", 64);
            signingKeyId = identifier(signingKeyId, "SIGNING_KEY", 255);
            signedDigest = digest(signedDigest, "SIGNED_ALLOCATION");
            signature = identifier(signature, "SIGNATURE", 4096);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
        }
    }

    record FinancialSummary(
            String organizationId,
            String accountId,
            String taskId,
            String currency,
            BigDecimal estimatedCostMinor,
            BigDecimal reservedCostMinor,
            BigDecimal postedCostMinor,
            BigDecimal finalCostMinor,
            BigDecimal recognizedRevenueMinor,
            BigDecimal collectedCashMinor,
            BigDecimal refundsMinor,
            BigDecimal grossProfitMinor,
            BigDecimal grossMarginRatio,
            long usageEntryCount,
            long unreconciledUsageCount,
            long revenueEntryCount,
            long unreconciledRevenueCount,
            Instant eventWatermark,
            Instant asOf,
            ReconciliationStatus reconciliationStatus,
            FinancialQualification qualification
    ) {
        public FinancialSummary {
            organizationId = identifier(
                    organizationId, "ORGANIZATION", DATABASE_ID_MAX_LENGTH);
            accountId = identifier(accountId, "ACCOUNT", DATABASE_ID_MAX_LENGTH);
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            currency = TaskFinopsPort.currency(currency);
            estimatedCostMinor = signedMoney(estimatedCostMinor, "ESTIMATED_COST");
            reservedCostMinor = signedMoney(reservedCostMinor, "RESERVED_COST");
            postedCostMinor = signedMoney(postedCostMinor, "POSTED_COST");
            finalCostMinor = signedMoney(finalCostMinor, "FINAL_COST");
            recognizedRevenueMinor = signedMoney(
                    recognizedRevenueMinor, "RECOGNIZED_REVENUE");
            collectedCashMinor = signedMoney(collectedCashMinor, "COLLECTED_CASH");
            refundsMinor = signedMoney(refundsMinor, "REFUNDS");
            grossProfitMinor = signedMoney(grossProfitMinor, "GROSS_PROFIT");
            if (grossMarginRatio != null && grossMarginRatio.scale() > 18) {
                throw new IllegalArgumentException("ELMOS_MTF_GROSS_MARGIN_SCALE_INVALID");
            }
            if (usageEntryCount < 0 || unreconciledUsageCount < 0
                    || revenueEntryCount < 0 || unreconciledRevenueCount < 0
                    || unreconciledUsageCount > usageEntryCount
                    || unreconciledRevenueCount > revenueEntryCount) {
                throw new IllegalArgumentException("ELMOS_MTF_FINANCIAL_COUNT_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
            Objects.requireNonNull(qualification, "qualification");
            if (reconciliationStatus == ReconciliationStatus.RECONCILED
                    && (unreconciledUsageCount != 0 || unreconciledRevenueCount != 0)) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_RECONCILED_SUMMARY_HAS_OPEN_ITEMS");
            }
            if (reconciliationStatus != ReconciliationStatus.RECONCILED
                    && qualification == FinancialQualification.CURRENT) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_CURRENT_SUMMARY_RECONCILIATION_REQUIRED");
            }
        }
    }

    record ControlCommand(
            AuthenticatedContext context,
            String taskId,
            String reasonCode,
            String idempotencyKey,
            String requestDigest
    ) {
        public ControlCommand {
            Objects.requireNonNull(context, "context");
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            reasonCode = identifier(reasonCode, "REASON", 96);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "CONTROL_REQUEST");
        }
    }

    record ManualReconciliationCommand(
            AuthenticatedContext context,
            String taskId,
            String reasonCode,
            String evidenceReference,
            String idempotencyKey
    ) {
        public ManualReconciliationCommand {
            Objects.requireNonNull(context, "context");
            taskId = identifier(taskId, "TASK", DATABASE_ID_MAX_LENGTH);
            reasonCode = identifier(reasonCode, "REASON", 96);
            evidenceReference = identifier(evidenceReference, "EVIDENCE_REFERENCE", 512);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
        }
    }

    ConcurrencyStatus concurrencyStatus(AuthenticatedContext context);

    List<TaskEvent> events(
            AuthenticatedContext context,
            String taskId,
            long afterSequence,
            int limit
    );

    Optional<ProgressSnapshot> progress(AuthenticatedContext context, String taskId);

    Optional<FinancialSummary> financialSummary(
            AuthenticatedContext context,
            String taskId,
            Instant asOf
    );

    String appendCheckpoint(Checkpoint checkpoint);

    String recordSideEffectReceipt(SideEffectReceipt receipt);

    String recordUsage(UsageEntry entry);

    String recordRevenue(RevenueEntry entry);

    String allocateRevenue(RevenueAllocation allocation);

    TaskFinopsPolicy.TaskState pause(ControlCommand command);

    TaskFinopsPolicy.TaskState resume(ControlCommand command);

    ReconciliationStatus requestManualReconciliation(ManualReconciliationCommand command);

    private static String identifier(String value, String field, int maxLength) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > maxLength
                || candidate.indexOf('\u0000') >= 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return candidate;
    }

    private static String optional(String value, int maxLength, String field) {
        if (value == null || value.isBlank()) return null;
        return identifier(value, field, maxLength);
    }

    private static String runIdentifier(String value) {
        String candidate = identifier(value, "RUN", 10);
        if (!candidate.matches("[1-9][0-9]{0,9}")) {
            throw new IllegalArgumentException("ELMOS_MTF_RUN_INVALID");
        }
        try {
            if (Integer.parseInt(candidate) < 1) {
                throw new NumberFormatException("non-positive");
            }
            return candidate;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException("ELMOS_MTF_RUN_INVALID");
        }
    }

    private static String digest(String value, String field) {
        String candidate = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
        if (candidate.startsWith("sha256:")) candidate = candidate.substring(7);
        if (!candidate.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return candidate;
    }

    private static String optionalDigest(String value, String field) {
        return value == null || value.isBlank() ? null : digest(value, field);
    }

    private static String currency(String value) {
        String candidate = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (!candidate.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("ELMOS_MTF_CURRENCY_INVALID");
        }
        return candidate;
    }

    private static BigDecimal nonNegativeDecimal(
            BigDecimal value,
            int maxScale,
            String field
    ) {
        BigDecimal candidate = decimal(value, maxScale, field);
        if (candidate.signum() < 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_NEGATIVE");
        }
        return candidate;
    }

    private static BigDecimal positiveDecimal(
            BigDecimal value,
            int maxScale,
            String field
    ) {
        BigDecimal candidate = decimal(value, maxScale, field);
        if (candidate.signum() <= 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_NON_POSITIVE");
        }
        return candidate;
    }

    private static BigDecimal signedMoney(BigDecimal value, String field) {
        return decimal(value, TaskFinopsPolicy.MONEY_SCALE, field);
    }

    private static BigDecimal nonZeroSignedMoney(BigDecimal value, String field) {
        BigDecimal candidate = signedMoney(value, field);
        if (candidate.signum() == 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_ZERO");
        }
        return candidate;
    }

    private static void requireRevenueSemantics(
            RevenueKind kind,
            RevenueState state,
            BigDecimal amountMinor,
            String correctionOfRevenueEntryId
    ) {
        boolean invalidSign = switch (kind) {
            case CHARGE, CASH_RECEIPT, REVENUE_RECOGNITION ->
                    amountMinor.signum() <= 0;
            case CREDIT, REFUND, TAX, PAYMENT_FEE, REVERSAL ->
                    amountMinor.signum() >= 0;
            case CORRECTION -> correctionOfRevenueEntryId == null;
        };
        if (invalidSign) {
            throw new IllegalArgumentException("ELMOS_MTF_REVENUE_SIGN_INVALID");
        }
        if (kind == RevenueKind.CASH_RECEIPT
                && state != RevenueState.COLLECTED
                && state != RevenueState.UNRECONCILED) {
            throw new IllegalArgumentException("ELMOS_MTF_REVENUE_STATE_INVALID");
        }
        if (kind == RevenueKind.REFUND
                && state != RevenueState.REFUNDED
                && state != RevenueState.UNRECONCILED) {
            throw new IllegalArgumentException("ELMOS_MTF_REVENUE_STATE_INVALID");
        }
        if ((kind == RevenueKind.TAX || kind == RevenueKind.PAYMENT_FEE)
                && state != RevenueState.RECORDED
                && state != RevenueState.POSTED
                && state != RevenueState.UNRECONCILED) {
            throw new IllegalArgumentException("ELMOS_MTF_REVENUE_STATE_INVALID");
        }
    }

    private static BigDecimal decimal(BigDecimal value, int maxScale, String field) {
        int integerDigits = value == null
                ? 0
                : Math.max(0, value.precision() - value.scale());
        if (value == null
                || value.scale() > maxScale
                || value.precision() > DATABASE_DECIMAL_MAX_PRECISION
                || integerDigits > DATABASE_DECIMAL_MAX_PRECISION - maxScale) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DECIMAL_INVALID");
        }
        return value;
    }

    private static void requireWindow(Instant start, Instant end) {
        Objects.requireNonNull(start, "periodStart");
        Objects.requireNonNull(end, "periodEnd");
        if (!end.isAfter(start)) {
            throw new IllegalArgumentException("ELMOS_MTF_PERIOD_INVALID");
        }
    }
}
