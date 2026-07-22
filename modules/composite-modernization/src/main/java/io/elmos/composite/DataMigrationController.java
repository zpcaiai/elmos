package io.elmos.composite;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class DataMigrationController {
    public enum WriteResult { SUCCEEDED, PARTIAL_WRITE, FAILED, DUPLICATE_SUPPRESSED }
    public enum ReadMode { LEGACY_ONLY, NEW_SHADOW_COMPARE, LEGACY_PRIMARY_NEW_FALLBACK, NEW_PRIMARY_LEGACY_FALLBACK, NEW_ONLY }
    public enum CutoverDecision { APPROVE_READ, APPROVE_WRITE, HOLD_LEGACY_PRIMARY, BLOCKED }

    public record DualWriteAttempt(boolean primarySucceeded, boolean secondarySucceeded,
                                   boolean sameTransaction, String idempotencyKey,
                                   boolean compensationAvailable, boolean outboxUsed,
                                   boolean auditRecorded) {}
    public record WriteDecision(WriteResult result, List<String> blockers, String recommendedPattern) {}

    public WriteDecision evaluateDualWrite(DualWriteAttempt attempt) {
        ArrayList<String> blockers = new ArrayList<>();
        if (attempt.idempotencyKey() == null || attempt.idempotencyKey().isBlank()) blockers.add("IDEMPOTENCY_KEY_MISSING");
        if (!attempt.auditRecorded()) blockers.add("WRITE_AUDIT_MISSING");
        if (attempt.primarySucceeded() && !attempt.secondarySucceeded()) blockers.add("PARTIAL_SECONDARY_WRITE");
        if (!attempt.sameTransaction() && !attempt.outboxUsed() && !attempt.compensationAvailable()) {
            blockers.add("SEQUENTIAL_DUAL_WRITE_WITHOUT_RECOVERY");
        }
        WriteResult result = attempt.primarySucceeded() && attempt.secondarySucceeded() && blockers.isEmpty()
                ? WriteResult.SUCCEEDED : attempt.primarySucceeded() && !attempt.secondarySucceeded()
                ? WriteResult.PARTIAL_WRITE : WriteResult.FAILED;
        String pattern = attempt.outboxUsed() ? "TRANSACTIONAL_OUTBOX" : "SINGLE_WRITER_PLUS_CDC_OR_COMPENSATION";
        return new WriteDecision(result, List.copyOf(blockers), pattern);
    }

    public record CdcStatus(String connectorRef, String sourcePosition, String appliedPosition,
                            long timeLagSeconds, long recordLag, long transactionLag,
                            long errorQueue, long retryQueue, boolean healthy,
                            boolean resumable, List<String> evidenceRefs) {
        public CdcStatus {
            require(connectorRef, "connectorRef"); require(sourcePosition, "sourcePosition");
            require(appliedPosition, "appliedPosition"); evidenceRefs = immutable(evidenceRefs);
            if (timeLagSeconds < 0 || recordLag < 0 || transactionLag < 0 || errorQueue < 0 || retryQueue < 0)
                throw new IllegalArgumentException("CDC lag and queue values must be non-negative");
        }
    }
    public record BackfillChunk(String chunkId, String lowerBound, String upperBound,
                                String status, long sourceCount, long targetCount,
                                String sourceHash, String targetHash, String checkpoint,
                                long rejectedRecords, boolean idempotentUpsert) {
        public BackfillChunk {
            require(chunkId, "chunkId");
            if (sourceCount < 0 || targetCount < 0 || rejectedRecords < 0)
                throw new IllegalArgumentException("backfill counts must be non-negative");
        }
    }
    public record Reconciliation(boolean structuralPassed, boolean partitionHashesPassed,
                                 boolean aggregatesPassed, boolean domainInvariantsPassed,
                                 boolean samplesPassed, List<String> differences,
                                 List<String> evidenceRefs) {
        public Reconciliation {
            differences = immutable(differences); evidenceRefs = immutable(evidenceRefs);
        }
        public boolean passed() {
            return structuralPassed && partitionHashesPassed && aggregatesPassed
                    && domainInvariantsPassed && samplesPassed && differences.isEmpty()
                    && !evidenceRefs.isEmpty();
        }
    }
    public record CutoverEvidence(List<BackfillChunk> chunks, CdcStatus cdc,
                                  Reconciliation reconciliation, long maximumLagSeconds,
                                  boolean targetPerformancePassed, boolean rollbackReady,
                                  boolean consumerReady, boolean newWriteIdempotencyPassed,
                                  boolean businessOwnerApproved, String cutoverFrontier,
                                  ReadMode requestedReadMode) {
        public CutoverEvidence {
            chunks = immutable(chunks); Objects.requireNonNull(cdc); Objects.requireNonNull(reconciliation);
            Objects.requireNonNull(requestedReadMode);
            if (maximumLagSeconds < 0) throw new IllegalArgumentException("maximumLagSeconds must be non-negative");
        }
    }
    public record DataCutoverResult(CutoverDecision decision, boolean readCutoverAllowed,
                                    boolean writeCutoverAllowed, List<String> blockers) {}

    public DataCutoverResult evaluateCutover(CutoverEvidence evidence) {
        ArrayList<String> readBlockers = new ArrayList<>();
        if (evidence.chunks().isEmpty() || evidence.chunks().stream().anyMatch(chunk -> !"COMPLETED".equals(chunk.status()))) {
            readBlockers.add("BACKFILL_INCOMPLETE");
        }
        if (evidence.chunks().stream().anyMatch(chunk -> chunk.sourceCount() != chunk.targetCount()
                || !Objects.equals(chunk.sourceHash(), chunk.targetHash()) || chunk.rejectedRecords() > 0
                || !chunk.idempotentUpsert() || chunk.checkpoint() == null || chunk.checkpoint().isBlank())) {
            readBlockers.add("BACKFILL_CHUNK_VALIDATION_FAILED");
        }
        if (!evidence.cdc().healthy() || !evidence.cdc().resumable() || evidence.cdc().evidenceRefs().isEmpty()) {
            readBlockers.add("CDC_UNHEALTHY_OR_UNRECOVERABLE");
        }
        if (evidence.cdc().timeLagSeconds() > evidence.maximumLagSeconds()
                || evidence.cdc().recordLag() > 0 || evidence.cdc().transactionLag() > 0) {
            readBlockers.add("CDC_LAG_EXCEEDED");
        }
        if (evidence.cdc().errorQueue() > 0 || evidence.cdc().retryQueue() > 0) readBlockers.add("CDC_QUEUE_NOT_DRAINED");
        if (!evidence.reconciliation().passed()) readBlockers.add("DATA_RECONCILIATION_FAILED");
        if (!evidence.targetPerformancePassed()) readBlockers.add("TARGET_PERFORMANCE_FAILED");
        if (!evidence.consumerReady()) readBlockers.add("CONSUMER_NOT_READY");
        if (evidence.cutoverFrontier() == null || evidence.cutoverFrontier().isBlank()) readBlockers.add("CUTOVER_FRONTIER_MISSING");
        boolean readAllowed = readBlockers.isEmpty();
        ArrayList<String> blockers = new ArrayList<>(readBlockers);
        if (!evidence.rollbackReady()) blockers.add("ROLLBACK_NOT_READY");
        if (!evidence.newWriteIdempotencyPassed()) blockers.add("NEW_WRITE_IDEMPOTENCY_FAILED");
        if (!evidence.businessOwnerApproved()) blockers.add("BUSINESS_OWNER_APPROVAL_REQUIRED");
        boolean writeAllowed = blockers.isEmpty();
        CutoverDecision decision = writeAllowed ? CutoverDecision.APPROVE_WRITE
                : readAllowed ? CutoverDecision.APPROVE_READ : CutoverDecision.HOLD_LEGACY_PRIMARY;
        return new DataCutoverResult(decision, readAllowed, writeAllowed, List.copyOf(blockers));
    }

    public static final class InboxIdempotency {
        private final Set<String> processed = new HashSet<>();
        public synchronized WriteResult accept(String messageId) {
            require(messageId, "messageId");
            return processed.add(messageId) ? WriteResult.SUCCEEDED : WriteResult.DUPLICATE_SUPPRESSED;
        }
        public synchronized int uniqueMessages() { return processed.size(); }
    }
}
