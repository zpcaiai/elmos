package io.elmos.workflow;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Bounded fault-injection plan for checkpoint and side-effect recovery.
 *
 * <p>The plan is intentionally provider-neutral: it enumerates the failure
 * boundaries and computes the policy decision that a runner adapter must
 * apply. It does not kill processes, call providers, or manufacture a crash
 * campaign receipt.</p>
 */
public final class TaskFinopsRecoveryCampaign {
    public static final String RUNTIME_EVIDENCE = "NOT_RUN";

    public enum FailureBoundary {
        BEFORE_CHECKPOINT,
        AFTER_CHECKPOINT,
        BEFORE_SIDE_EFFECT,
        AFTER_SIDE_EFFECT,
        AFTER_RECEIPT,
        LEASE_EXPIRED
    }

    public record FaultPoint(
            String checkpointId,
            FailureBoundary boundary,
            int attempt,
            long leaseGeneration
    ) {
        public FaultPoint {
            if (checkpointId == null || checkpointId.isBlank()
                    || attempt < 1 || leaseGeneration < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_FAULT_POINT_INVALID");
            }
            Objects.requireNonNull(boundary, "boundary");
        }
    }

    public record RecoveryPlan(
            FaultPoint faultPoint,
            TaskFinopsPolicy.RecoveryDecision decision,
            String reason,
            boolean requiresImmutableReceipt,
            String runtimeEvidence
    ) {
        public RecoveryPlan {
            Objects.requireNonNull(faultPoint, "faultPoint");
            Objects.requireNonNull(decision, "decision");
            if (reason == null || reason.isBlank()) {
                throw new IllegalArgumentException("ELMOS_MTF_RECOVERY_PLAN_INVALID");
            }
            if (!RUNTIME_EVIDENCE.equals(runtimeEvidence)) {
                throw new IllegalArgumentException("ELMOS_MTF_RECOVERY_EVIDENCE_INVALID");
            }
        }
    }

    public record CampaignPlan(List<RecoveryPlan> boundaries, String runtimeEvidence) {
        public CampaignPlan {
            boundaries = List.copyOf(Objects.requireNonNull(boundaries, "boundaries"));
            if (boundaries.isEmpty() || !RUNTIME_EVIDENCE.equals(runtimeEvidence)) {
                throw new IllegalArgumentException("ELMOS_MTF_CAMPAIGN_PLAN_INVALID");
            }
        }
    }

    private TaskFinopsRecoveryCampaign() {}

    /** Returns the complete bounded set of side-effect/checkpoint fault points. */
    public static List<FaultPoint> defaultFaultPoints(String checkpointId) {
        List<FaultPoint> points = new ArrayList<>();
        int attempt = 1;
        long generation = 1;
        for (FailureBoundary boundary : FailureBoundary.values()) {
            points.add(new FaultPoint(checkpointId, boundary, attempt, generation));
            attempt++;
            generation++;
        }
        return List.copyOf(points);
    }

    /**
     * Computes a recovery plan for one fault point. Unknown results without an
     * immutable receipt remain manual recovery; they are never blind retries.
     */
    public static RecoveryPlan evaluate(
            FaultPoint faultPoint,
            TaskFinopsPolicy.CheckpointIdentity expected,
            TaskFinopsPolicy.CheckpointIdentity actual,
            TaskFinopsPolicy.ErrorClass errorClass,
            boolean immutableReceiptProvesCompletion
    ) {
        Objects.requireNonNull(faultPoint, "faultPoint");
        TaskFinopsPolicy.RecoveryDecision decision = TaskFinopsPolicy.recover(
                Objects.requireNonNull(expected, "expected"),
                Objects.requireNonNull(actual, "actual"),
                Objects.requireNonNull(errorClass, "errorClass"),
                immutableReceiptProvesCompletion);
        String reason = switch (decision) {
            case RESUME_CHECKPOINT -> immutableReceiptProvesCompletion
                    ? "IMMUTABLE_RECEIPT_OR_COMPATIBLE_CHECKPOINT"
                    : "COMPATIBLE_CHECKPOINT_RETRYABLE_ERROR";
            case FORK_RUN -> "CHECKPOINT_COMPATIBILITY_MISMATCH";
            case MANUAL_RECOVERY -> "UNKNOWN_RESULT_WITHOUT_IMMUTABLE_RECEIPT";
            case RETRY_NODE -> "RETRYABLE_NODE_ERROR";
            case FAIL -> "NON_RETRYABLE_ERROR";
        };
        return new RecoveryPlan(faultPoint, decision, reason,
                errorClass == TaskFinopsPolicy.ErrorClass.UNKNOWN_RESULT,
                RUNTIME_EVIDENCE);
    }

    public static CampaignPlan plan(
            String checkpointId,
            TaskFinopsPolicy.CheckpointIdentity identity
    ) {
        Objects.requireNonNull(identity, "identity");
        List<RecoveryPlan> plans = new ArrayList<>();
        for (FaultPoint point : defaultFaultPoints(checkpointId)) {
            TaskFinopsPolicy.ErrorClass error = point.boundary()
                    == FailureBoundary.LEASE_EXPIRED
                    ? TaskFinopsPolicy.ErrorClass.UNKNOWN_RESULT
                    : TaskFinopsPolicy.ErrorClass.TRANSIENT;
            boolean receipt = point.boundary() == FailureBoundary.AFTER_RECEIPT;
            plans.add(evaluate(point, identity, identity, error, receipt));
        }
        return new CampaignPlan(plans, RUNTIME_EVIDENCE);
    }
}
