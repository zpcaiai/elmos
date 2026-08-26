package io.elmos.workflow;

import java.util.Objects;

/**
 * Provider-neutral guards for long workflow histories and duplicate starts.
 *
 * <p>The policy produces an adapter decision only. It never invokes a
 * workflow provider, performs Continue-As-New, or turns a duplicate request
 * into runtime evidence.</p>
 */
public final class TaskFinopsWorkflowHistoryPolicy {
    public static final String RUNTIME_EVIDENCE = "NOT_RUN";

    public enum HistoryDecision {
        KEEP_HISTORY,
        CONTINUE_AS_NEW,
        REJECT_TERMINAL_WORKFLOW
    }

    public enum StartDecision {
        START,
        RETURN_EXISTING,
        REJECT_PAYLOAD_CONFLICT,
        REQUIRE_RECONCILIATION
    }

    public enum ExistingOutcome {
        NONE,
        RUNNING,
        TERMINAL,
        UNKNOWN
    }

    public record HistoryLimits(int maxEvents, int maxPayloadBytes, int maxAttempts) {
        public HistoryLimits {
            if (maxEvents < 1 || maxPayloadBytes < 1 || maxAttempts < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_HISTORY_LIMITS_INVALID");
            }
        }
    }

    public record HistorySnapshot(
            String workflowId,
            int runNumber,
            int eventCount,
            int payloadBytes,
            int attemptCount,
            boolean terminal
    ) {
        public HistorySnapshot {
            if (workflowId == null || workflowId.isBlank() || runNumber < 1
                    || eventCount < 0 || payloadBytes < 0 || attemptCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_HISTORY_SNAPSHOT_INVALID");
            }
        }
    }

    public record HistoryDecisionResult(
            HistoryDecision decision,
            String reason,
            int nextRunNumber,
            String runtimeEvidence
    ) {
        public HistoryDecisionResult {
            Objects.requireNonNull(decision, "decision");
            if (reason == null || reason.isBlank() || nextRunNumber < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_HISTORY_DECISION_INVALID");
            }
            if (!RUNTIME_EVIDENCE.equals(runtimeEvidence)) {
                throw new IllegalArgumentException("ELMOS_MTF_HISTORY_EVIDENCE_INVALID");
            }
        }
    }

    public record ExistingStart(
            String workflowId,
            String payloadDigest,
            ExistingOutcome outcome
    ) {
        public ExistingStart {
            if (workflowId == null || workflowId.isBlank()
                    || payloadDigest == null || !payloadDigest.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("ELMOS_MTF_EXISTING_START_INVALID");
            }
            Objects.requireNonNull(outcome, "outcome");
        }
    }

    public record StartDecisionResult(
            StartDecision decision,
            String reason,
            String runtimeEvidence
    ) {
        public StartDecisionResult {
            Objects.requireNonNull(decision, "decision");
            if (reason == null || reason.isBlank()) {
                throw new IllegalArgumentException("ELMOS_MTF_START_DECISION_INVALID");
            }
            if (!RUNTIME_EVIDENCE.equals(runtimeEvidence)) {
                throw new IllegalArgumentException("ELMOS_MTF_START_EVIDENCE_INVALID");
            }
        }
    }

    private TaskFinopsWorkflowHistoryPolicy() {}

    public static HistoryDecisionResult evaluateHistory(
            HistorySnapshot snapshot,
            HistoryLimits limits
    ) {
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(limits, "limits");
        if (snapshot.terminal()) {
            return new HistoryDecisionResult(
                    HistoryDecision.REJECT_TERMINAL_WORKFLOW,
                    "TERMINAL_HISTORY_CANNOT_CONTINUE_AS_NEW",
                    snapshot.runNumber(), RUNTIME_EVIDENCE);
        }
        if (snapshot.attemptCount() >= limits.maxAttempts()) {
            return new HistoryDecisionResult(
                    HistoryDecision.REJECT_TERMINAL_WORKFLOW,
                    "MAX_ATTEMPTS_REACHED",
                    snapshot.runNumber(), RUNTIME_EVIDENCE);
        }
        boolean eventLimit = snapshot.eventCount() >= limits.maxEvents();
        boolean payloadLimit = snapshot.payloadBytes() >= limits.maxPayloadBytes();
        if (eventLimit || payloadLimit) {
            return new HistoryDecisionResult(
                    HistoryDecision.CONTINUE_AS_NEW,
                    eventLimit && payloadLimit
                            ? "EVENT_AND_PAYLOAD_LIMIT_REACHED"
                            : eventLimit ? "EVENT_LIMIT_REACHED" : "PAYLOAD_LIMIT_REACHED",
                    Math.addExact(snapshot.runNumber(), 1), RUNTIME_EVIDENCE);
        }
        return new HistoryDecisionResult(
                HistoryDecision.KEEP_HISTORY, "WITHIN_HISTORY_LIMITS",
                snapshot.runNumber(), RUNTIME_EVIDENCE);
    }

    public static StartDecisionResult evaluateStart(
            TaskFinopsWorkflowStartPayload payload,
            ExistingStart existing
    ) {
        Objects.requireNonNull(payload, "payload");
        if (existing == null || existing.outcome() == ExistingOutcome.NONE) {
            return new StartDecisionResult(
                    StartDecision.START, "NO_DURABLE_START_RECORD", RUNTIME_EVIDENCE);
        }
        if (!payload.payload().workflowId().equals(existing.workflowId())) {
            return new StartDecisionResult(
                    StartDecision.REJECT_PAYLOAD_CONFLICT,
                    "WORKFLOW_ID_CONFLICT", RUNTIME_EVIDENCE);
        }
        if (!payload.payloadDigest().equals(existing.payloadDigest())) {
            return new StartDecisionResult(
                    StartDecision.REJECT_PAYLOAD_CONFLICT,
                    "PAYLOAD_DIGEST_CONFLICT", RUNTIME_EVIDENCE);
        }
        return switch (existing.outcome()) {
            case RUNNING, TERMINAL -> new StartDecisionResult(
                    StartDecision.RETURN_EXISTING,
                    "IDEMPOTENT_START_REPLAY", RUNTIME_EVIDENCE);
            case UNKNOWN -> new StartDecisionResult(
                    StartDecision.REQUIRE_RECONCILIATION,
                    "UNKNOWN_START_OUTCOME", RUNTIME_EVIDENCE);
            case NONE -> throw new IllegalStateException("unreachable");
        };
    }
}
