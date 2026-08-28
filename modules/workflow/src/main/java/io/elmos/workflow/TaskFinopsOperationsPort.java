package io.elmos.workflow;

import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Durable adapter boundary for the repository-owned task FinOps closure.
 *
 * <p>Every command carries a context derived from authenticated membership.
 * External provider observations are inputs to reconciliation only; this port
 * cannot certify, deploy, move money, delete provider data, or manufacture an
 * independent receipt.</p>
 */
public interface TaskFinopsOperationsPort {
    // A source row can expand to one hourly and one daily bucket. Keeping the
    // source bound at 10k also keeps the worst-case run and 20k bucket payload
    // inside the database publication limits.
    int MAX_ANALYTICS_SOURCE_ROWS = 10_000;

    record FeatureRolloutCommand(
            TaskFinopsPort.AuthenticatedContext context,
            TaskFinopsFeatureRollout.Environment environment,
            String featureKey,
            TaskFinopsFeatureRollout.Stage stage,
            int exposurePercent,
            long expectedVersion,
            String idempotencyKey,
            String requestDigest
    ) {
        public FeatureRolloutCommand {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(environment, "environment");
            featureKey = identifier(featureKey, "FEATURE", 96);
            Objects.requireNonNull(stage, "stage");
            new TaskFinopsFeatureRollout.FlagState(stage, exposurePercent);
            if (expectedVersion < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_FEATURE_VERSION_INVALID");
            }
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record CheckpointCompatibilityCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String decisionId,
            String checkpointId,
            CheckpointForkPolicy.DecisionType decisionType,
            String fingerprintDigest,
            List<CheckpointForkPolicy.ReasonCode> reasonCodes,
            String evidenceDigest,
            String signatureAlgorithm,
            String signingKeyId,
            String signature
    ) {
        public CheckpointCompatibilityCommand {
            Objects.requireNonNull(context, "context");
            decisionId = identifier(decisionId, "DECISION", 96);
            checkpointId = identifier(checkpointId, "CHECKPOINT", 96);
            Objects.requireNonNull(decisionType, "decisionType");
            if (decisionType != CheckpointForkPolicy.DecisionType.RESUME_EXISTING_RUN
                    && decisionType != CheckpointForkPolicy.DecisionType.CREATE_FORK_RUN) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_CHECKPOINT_DECISION_NOT_FINAL");
            }
            fingerprintDigest = digest(fingerprintDigest, "FINGERPRINT");
            reasonCodes = List.copyOf(Objects.requireNonNull(reasonCodes, "reasonCodes"));
            if (reasonCodes.isEmpty() || reasonCodes.size() > 16) {
                throw new IllegalArgumentException("ELMOS_MTF_CHECKPOINT_REASON_INVALID");
            }
            boolean compatible = decisionType
                    == CheckpointForkPolicy.DecisionType.RESUME_EXISTING_RUN;
            boolean exactCompatibleReason = reasonCodes.equals(
                    List.of(CheckpointForkPolicy.ReasonCode.COMPATIBLE));
            boolean hasIncompatibility = reasonCodes.stream().anyMatch(reason -> switch (reason) {
                case INPUT_MANIFEST_MISMATCH, REPOSITORY_REVISION_MISMATCH,
                     TOOLCHAIN_MISMATCH, MODEL_MISMATCH, SCHEMA_VERSION_MISMATCH -> true;
                default -> false;
            });
            if ((compatible && !exactCompatibleReason)
                    || (!compatible && (!hasIncompatibility
                    || reasonCodes.contains(CheckpointForkPolicy.ReasonCode.COMPATIBLE)))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_CHECKPOINT_REASON_DECISION_MISMATCH");
            }
            evidenceDigest = digest(evidenceDigest, "EVIDENCE");
            signatureAlgorithm = identifier(signatureAlgorithm, "SIGNATURE_ALGORITHM", 64);
            signingKeyId = identifier(signingKeyId, "SIGNING_KEY", 255);
            signature = identifier(signature, "SIGNATURE", 4096);
        }

        public String databaseDecision() {
            return decisionType == CheckpointForkPolicy.DecisionType.RESUME_EXISTING_RUN
                    ? "COMPATIBLE" : "INCOMPATIBLE";
        }
    }

    record ForkRecoveryCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String recoveryForkId,
            String parentTaskId,
            String checkpointId,
            String compatibilityDecisionId,
            String childTaskId,
            String idempotencyKey,
            String requestDigest
    ) {
        public ForkRecoveryCommand {
            Objects.requireNonNull(context, "context");
            recoveryForkId = identifier(recoveryForkId, "RECOVERY_FORK", 96);
            parentTaskId = identifier(parentTaskId, "PARENT_TASK", 96);
            checkpointId = identifier(checkpointId, "CHECKPOINT", 96);
            compatibilityDecisionId = identifier(
                    compatibilityDecisionId, "COMPATIBILITY_DECISION", 96);
            childTaskId = identifier(childTaskId, "CHILD_TASK", 96);
            if (parentTaskId.equals(childTaskId)) {
                throw new IllegalArgumentException("ELMOS_MTF_FORK_TASK_MUST_BE_NEW");
            }
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 140);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record RecoveryForkResult(
            String recoveryForkId,
            String parentTaskId,
            String checkpointId,
            String compatibilityDecisionId,
            String childTaskId,
            long parentRunNumber,
            long childRunNumber,
            Instant createdAt
    ) {
        public RecoveryForkResult {
            recoveryForkId = identifier(recoveryForkId, "RECOVERY_FORK", 96);
            parentTaskId = identifier(parentTaskId, "PARENT_TASK", 96);
            checkpointId = identifier(checkpointId, "CHECKPOINT", 96);
            compatibilityDecisionId = identifier(
                    compatibilityDecisionId, "COMPATIBILITY_DECISION", 96);
            childTaskId = identifier(childTaskId, "CHILD_TASK", 96);
            if (parentRunNumber < 1 || childRunNumber < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_RECOVERY_RUN_INVALID");
            }
            Objects.requireNonNull(createdAt, "createdAt");
        }
    }

    record LifecycleRequestCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String lifecycleJobId,
            TenantLifecyclePolicy.Operation operation,
            TenantLifecyclePolicy.ExportFormat exportFormat,
            Instant retentionCutoff,
            String idempotencyKey,
            String requestDigest
    ) {
        public LifecycleRequestCommand {
            Objects.requireNonNull(context, "context");
            lifecycleJobId = identifier(lifecycleJobId, "LIFECYCLE_JOB", 96);
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(exportFormat, "exportFormat");
            Objects.requireNonNull(retentionCutoff, "retentionCutoff");
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record LifecycleStatus(
            String lifecycleJobId,
            String organizationId,
            String accountId,
            TenantLifecyclePolicy.Operation operation,
            TenantLifecyclePolicy.ExportFormat exportFormat,
            String state,
            Instant retentionCutoff,
            String pageCursor,
            String manifestDigest,
            long rowCount,
            long byteCount,
            TenantLifecyclePolicy.ProviderResult providerResult,
            String failureCode,
            long stateVersion,
            Instant requestedAt,
            Instant completedAt
    ) {
        public LifecycleStatus {
            lifecycleJobId = identifier(lifecycleJobId, "LIFECYCLE_JOB", 96);
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(exportFormat, "exportFormat");
            state = identifier(state, "LIFECYCLE_STATE", 24);
            Objects.requireNonNull(retentionCutoff, "retentionCutoff");
            pageCursor = optional(pageCursor, "PAGE_CURSOR", 512);
            manifestDigest = optionalDigest(manifestDigest, "MANIFEST");
            if (rowCount < 0 || byteCount < 0 || stateVersion < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_LIFECYCLE_STATUS_INVALID");
            }
            Objects.requireNonNull(providerResult, "providerResult");
            failureCode = optional(failureCode, "FAILURE_CODE", 96);
            Objects.requireNonNull(requestedAt, "requestedAt");
            if (("COMPLETED".equals(state)) != (completedAt != null)) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_LIFECYCLE_COMPLETION_SHAPE_INVALID");
            }
        }
    }

    record LifecycleTransitionCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String lifecycleJobId,
            long expectedVersion,
            String nextState,
            String pageCursor,
            String manifestDigest,
            long rowCount,
            long byteCount,
            TenantLifecyclePolicy.ProviderResult providerResult,
            String failureCode,
            String idempotencyKey,
            String requestDigest
    ) {
        public LifecycleTransitionCommand {
            Objects.requireNonNull(context, "context");
            lifecycleJobId = identifier(lifecycleJobId, "LIFECYCLE_JOB", 96);
            if (expectedVersion < 1 || rowCount < 0 || byteCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_LIFECYCLE_TRANSITION_INVALID");
            }
            nextState = identifier(nextState, "LIFECYCLE_STATE", 24);
            pageCursor = optional(pageCursor, "PAGE_CURSOR", 512);
            manifestDigest = optionalDigest(manifestDigest, "MANIFEST");
            Objects.requireNonNull(providerResult, "providerResult");
            failureCode = optional(failureCode, "FAILURE_CODE", 96);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    /**
     * Append-only export progress.  A page checkpoint binds its exact bytes,
     * cursor and cumulative counts before a lifecycle job can publish a
     * terminal manifest.
     */
    record ExportPageCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String lifecycleJobId,
            long pageNumber,
            String cursorDigest,
            long rowCount,
            long byteCount,
            long cumulativeRowCount,
            long cumulativeByteCount,
            boolean terminal,
            String pageDigest,
            long expectedVersion,
            String idempotencyKey,
            String requestDigest
    ) {
        public ExportPageCommand {
            Objects.requireNonNull(context, "context");
            lifecycleJobId = identifier(lifecycleJobId, "LIFECYCLE_JOB", 96);
            if (pageNumber < 1 || rowCount < 0 || byteCount < 0
                    || cumulativeRowCount < rowCount
                    || cumulativeByteCount < byteCount
                    || expectedVersion < 1) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_EXPORT_PAGE_CHECKPOINT_INVALID");
            }
            cursorDigest = digest(cursorDigest, "EXPORT_CURSOR");
            pageDigest = digest(pageDigest, "EXPORT_PAGE");
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record PurgeResultCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String purgeReceiptId,
            String lifecycleJobId,
            String contentObjectId,
            String providerResult,
            String providerReference,
            String evidenceDigest,
            long expectedVersion,
            String idempotencyKey,
            String requestDigest
    ) {
        public PurgeResultCommand {
            Objects.requireNonNull(context, "context");
            purgeReceiptId = identifier(purgeReceiptId, "PURGE_RECEIPT", 96);
            lifecycleJobId = identifier(lifecycleJobId, "LIFECYCLE_JOB", 96);
            contentObjectId = identifier(contentObjectId, "CONTENT_OBJECT", 96);
            providerResult = identifier(providerResult, "PROVIDER_RESULT", 24);
            providerReference = optional(providerReference, "PROVIDER_REFERENCE", 255);
            evidenceDigest = optionalDigest(evidenceDigest, "EVIDENCE");
            if (expectedVersion < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_PURGE_VERSION_INVALID");
            }
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record SettlementCommand(
            TaskFinopsPort.AuthenticatedContext context,
            PaymentSettlementReconciler.ReconciliationRequest reconciliation,
            String provider,
            String externalEvidenceDigest,
            String evidenceVerifierActorId,
            String idempotencyKey,
            String requestDigest
    ) {
        public SettlementCommand {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(reconciliation, "reconciliation");
            if (!context.actorId().equals(reconciliation.reconciledByActorId())) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_SETTLEMENT_RECONCILER_CONTEXT_MISMATCH");
            }
            provider = identifier(provider, "PROVIDER", 64);
            externalEvidenceDigest = optionalDigest(
                    externalEvidenceDigest, "EXTERNAL_EVIDENCE");
            evidenceVerifierActorId = optional(
                    evidenceVerifierActorId, "EVIDENCE_VERIFIER", 128);
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            if (!idempotencyKey.equals(reconciliation.idempotencyKey())) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_SETTLEMENT_IDEMPOTENCY_SCOPE_MISMATCH");
            }
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record SettlementReceipt(
            String reconciliationId,
            PaymentSettlementReconciler.ReconciliationStatus status,
            String currency,
            Instant periodStart,
            Instant periodEnd,
            java.math.BigDecimal providerReportedMinor,
            java.math.BigDecimal ledgerRecordedMinor,
            java.math.BigDecimal differenceMinor,
            Instant recordedAt
    ) {
        public SettlementReceipt {
            reconciliationId = identifier(reconciliationId, "RECONCILIATION", 96);
            Objects.requireNonNull(status, "status");
            if (currency == null || !currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_SETTLEMENT_CURRENCY_INVALID");
            }
            Objects.requireNonNull(periodStart, "periodStart");
            Objects.requireNonNull(periodEnd, "periodEnd");
            if (!periodEnd.isAfter(periodStart)
                    || ledgerRecordedMinor == null
                    || !fitsSettlementMoney(ledgerRecordedMinor)
                    || (providerReportedMinor != null
                    && !fitsSettlementMoney(providerReportedMinor))
                    || (differenceMinor != null
                    && !fitsSettlementMoney(differenceMinor))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_SETTLEMENT_RECEIPT_INVALID");
            }
            if ((providerReportedMinor == null) != (differenceMinor == null)
                    || (status == PaymentSettlementReconciler.ReconciliationStatus.UNKNOWN
                    && providerReportedMinor != null)
                    || (status == PaymentSettlementReconciler.ReconciliationStatus.RECONCILED
                    && (providerReportedMinor == null
                    || differenceMinor.signum() != 0))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_SETTLEMENT_RECEIPT_SHAPE_INVALID");
            }
            Objects.requireNonNull(recordedAt, "recordedAt");
        }
    }

    record AnalyticsWindow(
            TaskFinopsPort.AuthenticatedContext context,
            Instant windowStart,
            Instant windowEnd,
            int limit
    ) {
        public AnalyticsWindow {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(windowStart, "windowStart");
            Objects.requireNonNull(windowEnd, "windowEnd");
            if (!windowEnd.isAfter(windowStart)
                    || windowEnd.isAfter(windowStart.plusSeconds(366L * 86_400L))
                    || limit < 1 || limit > MAX_ANALYTICS_SOURCE_ROWS) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_WINDOW_INVALID");
            }
        }
    }

    /** Journal and financial facts read from one repeatable database snapshot. */
    record AnalyticsSource(
            List<TaskFinopsAnalytics.JournalEvent> journal,
            List<TaskFinopsAnalytics.FinancialFact> financialFacts
    ) {
        public AnalyticsSource {
            journal = List.copyOf(Objects.requireNonNull(journal, "journal"));
            financialFacts = List.copyOf(Objects.requireNonNull(
                    financialFacts, "financialFacts"));
            if (journal.size() > MAX_ANALYTICS_SOURCE_ROWS
                    || financialFacts.size() > MAX_ANALYTICS_SOURCE_ROWS) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_SOURCE_LIMIT_EXCEEDED");
            }
        }
    }

    record ProjectionPublication(
            TaskFinopsPort.AuthenticatedContext context,
            String rebuildId,
            Instant windowStart,
            Instant windowEnd,
            long expectedGeneration,
            TaskFinopsAnalytics.RebuildResult journal,
            TaskFinopsAnalytics.AggregationResult hourly,
            TaskFinopsAnalytics.AggregationResult daily,
            String idempotencyKey,
            String requestDigest
    ) {
        public ProjectionPublication {
            Objects.requireNonNull(context, "context");
            rebuildId = identifier(rebuildId, "REBUILD", 96);
            Objects.requireNonNull(windowStart, "windowStart");
            Objects.requireNonNull(windowEnd, "windowEnd");
            if (expectedGeneration < 0 || !windowEnd.isAfter(windowStart)
                    || windowEnd.isAfter(windowStart.plusSeconds(366L * 86_400L))) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_PUBLICATION_INVALID");
            }
            Objects.requireNonNull(journal, "journal");
            Objects.requireNonNull(hourly, "hourly");
            Objects.requireNonNull(daily, "daily");
            requireScope(context, journal.organizationId(), journal.accountId());
            requireScope(context, hourly.organizationId(), hourly.accountId());
            requireScope(context, daily.organizationId(), daily.accountId());
            if (hourly.grain() != TaskFinopsAnalytics.Grain.HOUR
                    || daily.grain() != TaskFinopsAnalytics.Grain.DAY) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_GRAIN_INVALID");
            }
            if (journal.inputContinuity() != TaskFinopsAnalytics.InputContinuity.COMPLETE) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_INPUT_CONTINUITY_INCOMPLETE");
            }
            if (journal.eventCount() > MAX_ANALYTICS_SOURCE_ROWS
                    || journal.runs().size() > MAX_ANALYTICS_SOURCE_ROWS
                    || hourly.factCount() > MAX_ANALYTICS_SOURCE_ROWS
                    || daily.factCount() > MAX_ANALYTICS_SOURCE_ROWS
                    || hourly.rows().size() > 50_000
                    || daily.rows().size() > 50_000
                    || hourly.factCount() != daily.factCount()
                    || !hourly.asOf().equals(daily.asOf())
                    || !journal.asOf().isBefore(windowEnd)
                    || (hourly.factCount() > 0 && !hourly.asOf().isBefore(windowEnd))
                    || hourly.rows().stream().anyMatch(row ->
                    !row.bucketEnd().isAfter(windowStart)
                            || !row.bucketStart().isBefore(windowEnd))
                    || daily.rows().stream().anyMatch(row ->
                    !row.bucketEnd().isAfter(windowStart)
                            || !row.bucketStart().isBefore(windowEnd))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_PUBLICATION_SOURCE_MISMATCH");
            }
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY", 160);
            requestDigest = digest(requestDigest, "REQUEST");
        }
    }

    record ProjectionSnapshot(
            String rebuildId,
            long generation,
            Instant sourceAsOf,
            TaskFinopsAnalytics.InputContinuity inputContinuity,
            TaskFinopsAnalytics.ExternalEvidenceState externalEvidence,
            TaskFinopsAnalytics.ProviderOutcome providerOutcome,
            TaskFinopsAnalytics.ProductionCertification productionCertification,
            String hourlyChecksum,
            String dailyChecksum,
            List<TaskFinopsAnalytics.AggregateBucket> buckets
    ) {
        public ProjectionSnapshot {
            rebuildId = identifier(rebuildId, "REBUILD", 96);
            if (generation < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_GENERATION_INVALID");
            }
            Objects.requireNonNull(sourceAsOf, "sourceAsOf");
            Objects.requireNonNull(inputContinuity, "inputContinuity");
            if (externalEvidence != TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN
                    || providerOutcome != TaskFinopsAnalytics.ProviderOutcome.UNKNOWN
                    || productionCertification
                    != TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_SAFETY_BOUNDARY_INVALID");
            }
            hourlyChecksum = digest(hourlyChecksum, "HOURLY");
            dailyChecksum = digest(dailyChecksum, "DAILY");
            buckets = List.copyOf(Objects.requireNonNull(buckets, "buckets"));
        }
    }

    long setFeatureRollout(FeatureRolloutCommand command);

    String recordCheckpointCompatibility(CheckpointCompatibilityCommand command);

    RecoveryForkResult forkRecovery(ForkRecoveryCommand command);

    String requestLifecycle(LifecycleRequestCommand command);

    Optional<LifecycleStatus> lifecycleStatus(
            TaskFinopsPort.AuthenticatedContext context, String lifecycleJobId);

    long advanceLifecycle(LifecycleTransitionCommand command);

    long checkpointExportPage(ExportPageCommand command);

    long recordPurgeResult(PurgeResultCommand command);

    SettlementReceipt recordSettlement(SettlementCommand command);

    AnalyticsSource analyticsSource(AnalyticsWindow window);

    List<TaskFinopsAnalytics.JournalEvent> journal(AnalyticsWindow window);

    List<TaskFinopsAnalytics.FinancialFact> financialFacts(AnalyticsWindow window);

    long currentProjectionGeneration(TaskFinopsPort.AuthenticatedContext context);

    long publishProjection(ProjectionPublication publication);

    Optional<ProjectionSnapshot> currentProjection(
            TaskFinopsPort.AuthenticatedContext context,
            TaskFinopsAnalytics.Grain grain,
            Instant from,
            Instant to,
            int limit);

    private static void requireScope(
            TaskFinopsPort.AuthenticatedContext context,
            String organizationId,
            String accountId
    ) {
        if (!context.organizationId().equals(organizationId)
                || !context.accountId().equals(accountId)) {
            throw new IllegalArgumentException("ELMOS_MTF_ACCOUNT_SCOPE_MISMATCH");
        }
    }

    private static String identifier(String value, String field, int max) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > max
                || candidate.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return candidate;
    }

    private static String optional(String value, String field, int max) {
        return value == null || value.isBlank() ? null : identifier(value, field, max);
    }

    private static String digest(String value, String field) {
        String candidate = value == null ? "" : value.trim().toLowerCase(java.util.Locale.ROOT);
        if (candidate.startsWith("sha256:")) candidate = candidate.substring(7);
        if (!candidate.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return candidate;
    }

    private static String optionalDigest(String value, String field) {
        return value == null || value.isBlank() ? null : digest(value, field);
    }

    private static boolean fitsSettlementMoney(java.math.BigDecimal value) {
        int integerDigits = Math.max(0, value.precision() - value.scale());
        return value.scale() <= PaymentSettlementReconciler.MONEY_SCALE
                && value.precision() <= PaymentSettlementReconciler.MONEY_PRECISION
                && integerDigits <= PaymentSettlementReconciler.MONEY_PRECISION
                - PaymentSettlementReconciler.MONEY_SCALE;
    }
}
