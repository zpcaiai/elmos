package io.elmos.composite;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class SystemCutoverOrchestrator {
    public enum StepType { CHECK, APPROVAL, DEPLOY, CONFIGURE, START_SYNC, WAIT_LAG,
        RUN_RECONCILIATION, SHIFT_TRAFFIC, SWITCH_READ, SWITCH_WRITE, VERIFY, HOLD,
        ROLLBACK, DECOMMISSION }
    public enum RollbackLevel { TRAFFIC_ONLY, READ_ROLLBACK, WRITE_ROLLBACK,
        APPLICATION_ROLLBACK, DATA_REPAIR, FULL_SYSTEM_ROLLBACK, FORWARD_FIX }

    public record FrozenManifest(String cutoverPlanId, String organizationId, String landscapeId,
                                 String repositoryCommitSetHash, String artifactDigestSetHash,
                                 String contractSnapshotId, String compatibilityRuntimeHash,
                                 String dataFrontier, String trafficPlanId, String validationProfileHash,
                                 String rollbackPlanId, Instant frozenAt, List<String> approvedBy,
                                 List<String> evidenceRefs) {
        public FrozenManifest {
            require(cutoverPlanId, "cutoverPlanId"); require(organizationId, "organizationId");
            require(landscapeId, "landscapeId"); require(repositoryCommitSetHash, "repositoryCommitSetHash");
            require(artifactDigestSetHash, "artifactDigestSetHash"); require(contractSnapshotId, "contractSnapshotId");
            require(compatibilityRuntimeHash, "compatibilityRuntimeHash"); require(dataFrontier, "dataFrontier");
            require(trafficPlanId, "trafficPlanId"); require(validationProfileHash, "validationProfileHash");
            require(rollbackPlanId, "rollbackPlanId"); Objects.requireNonNull(frozenAt);
            approvedBy = immutable(approvedBy); evidenceRefs = immutable(evidenceRefs);
        }
    }
    public record CutoverStep(String stepId, StepType stepType, List<String> preconditions,
                              List<String> validations, RollbackClassification rollbackClassification,
                              boolean productionWrite, boolean destructive, boolean humanApproved,
                              List<String> evidenceRefs) {
        public CutoverStep {
            require(stepId, "stepId"); Objects.requireNonNull(stepType); preconditions = immutable(preconditions);
            validations = immutable(validations); Objects.requireNonNull(rollbackClassification);
            evidenceRefs = immutable(evidenceRefs);
        }
    }
    public record StepDecision(String stepId, boolean allowed, List<String> blockers,
                               CompositeState nextState) {}

    public StepDecision evaluateStep(CompositeState current, FrozenManifest manifest,
                                     CutoverStep step, boolean inputsStillMatchFreeze,
                                     boolean gatesPassed) {
        ArrayList<String> blockers = new ArrayList<>();
        if (manifest.evidenceRefs().isEmpty()) blockers.add("FROZEN_MANIFEST_EVIDENCE_MISSING");
        if (manifest.approvedBy().isEmpty()) blockers.add("FROZEN_MANIFEST_APPROVAL_MISSING");
        if (!inputsStillMatchFreeze) blockers.add("REVALIDATION_REQUIRED");
        if (!gatesPassed || step.validations().isEmpty()) blockers.add("CUTOVER_GATES_FAILED");
        if ((step.productionWrite() || step.destructive()) && !step.humanApproved()) blockers.add("HUMAN_APPROVAL_REQUIRED");
        if (step.evidenceRefs().isEmpty()) blockers.add("CUTOVER_STEP_EVIDENCE_MISSING");
        CompositeState next = nextState(step.stepType());
        if (!allowedTransition(current, next)) blockers.add("INVALID_CUTOVER_STATE_TRANSITION");
        return new StepDecision(step.stepId(), blockers.isEmpty(), List.copyOf(blockers),
                blockers.isEmpty() ? next : CompositeState.CUTOVER_PAUSED);
    }

    public record RollbackContext(boolean newWritesExist, boolean legacyCanReadNewData,
                                  boolean reverseCdcReady, boolean dataRepairApproved,
                                  boolean externalEventsIrreversible, List<String> evidenceRefs) {}
    public record RollbackDecision(RollbackLevel level, RollbackClassification classification,
                                   List<String> blockers) {}

    public RollbackDecision rollback(RollbackContext context) {
        ArrayList<String> blockers = new ArrayList<>();
        if (context.evidenceRefs().isEmpty()) blockers.add("ROLLBACK_EVIDENCE_MISSING");
        if (!context.newWritesExist()) return new RollbackDecision(RollbackLevel.TRAFFIC_ONLY,
                RollbackClassification.REVERSIBLE, List.copyOf(blockers));
        if (context.legacyCanReadNewData() && context.reverseCdcReady()) return new RollbackDecision(
                RollbackLevel.WRITE_ROLLBACK, RollbackClassification.REVERSIBLE_WITH_DATA_REPAIR,
                List.copyOf(blockers));
        if (context.dataRepairApproved()) return new RollbackDecision(RollbackLevel.DATA_REPAIR,
                RollbackClassification.REVERSIBLE_WITH_DATA_REPAIR, List.copyOf(blockers));
        blockers.add("LEGACY_CANNOT_READ_NEW_WRITES");
        if (context.externalEventsIrreversible()) blockers.add("EXTERNAL_EVENTS_IRREVERSIBLE");
        return new RollbackDecision(RollbackLevel.FORWARD_FIX,
                context.externalEventsIrreversible() ? RollbackClassification.IRREVERSIBLE
                        : RollbackClassification.FORWARD_FIX_ONLY, List.copyOf(blockers));
    }

    public record StabilityHold(Instant startsAt, Duration requiredDuration, Instant evaluatedAt,
                                boolean elevatedObservability, boolean legacyArtifactsRetained,
                                boolean compatibilityRuntimeRetained, boolean rollbackRetained,
                                List<String> evidenceRefs) {
        public boolean completed() { return !evaluatedAt.isBefore(startsAt.plus(requiredDuration)); }
    }
    public record DecommissionEvidence(boolean legacyTrafficZero, boolean legacyConsumersZero,
                                       boolean legacyDatabaseWritesZero, boolean legacyBatchAccessZero,
                                       boolean credentialRevocationPlanned, boolean dataArchived,
                                       boolean legalHoldChecked, boolean auditRetentionConfirmed,
                                       boolean evidencePackComplete, boolean assetOwnerApproved,
                                       boolean costConfirmed, boolean cmdbUpdated,
                                       boolean stabilityHoldCompleted, List<String> evidenceRefs) {
        public DecommissionEvidence { evidenceRefs = immutable(evidenceRefs); }
    }
    public record DecommissionDecision(boolean allowed, List<String> blockers,
                                       CompositeState state, List<String> permittedActions) {}

    public DecommissionDecision decommission(DecommissionEvidence evidence) {
        ArrayList<String> blockers = new ArrayList<>();
        requireGate(evidence.legacyTrafficZero(), "LEGACY_TRAFFIC_PRESENT", blockers);
        requireGate(evidence.legacyConsumersZero(), "LEGACY_CONSUMER_PRESENT", blockers);
        requireGate(evidence.legacyDatabaseWritesZero(), "LEGACY_DATABASE_WRITE_PRESENT", blockers);
        requireGate(evidence.legacyBatchAccessZero(), "LEGACY_BATCH_ACCESS_PRESENT", blockers);
        requireGate(evidence.credentialRevocationPlanned(), "CREDENTIAL_REVOCATION_PLAN_MISSING", blockers);
        requireGate(evidence.dataArchived(), "DATA_ARCHIVE_MISSING", blockers);
        requireGate(evidence.legalHoldChecked(), "LEGAL_HOLD_NOT_CHECKED", blockers);
        requireGate(evidence.auditRetentionConfirmed(), "AUDIT_RETENTION_UNCONFIRMED", blockers);
        requireGate(evidence.evidencePackComplete(), "EVIDENCE_PACK_INCOMPLETE", blockers);
        requireGate(evidence.assetOwnerApproved(), "ASSET_OWNER_APPROVAL_REQUIRED", blockers);
        requireGate(evidence.costConfirmed(), "COST_CONFIRMATION_MISSING", blockers);
        requireGate(evidence.cmdbUpdated(), "CMDB_UPDATE_MISSING", blockers);
        requireGate(evidence.stabilityHoldCompleted(), "STABILITY_HOLD_INCOMPLETE", blockers);
        if (evidence.evidenceRefs().isEmpty()) blockers.add("DECOMMISSION_EVIDENCE_MISSING");
        return new DecommissionDecision(blockers.isEmpty(), List.copyOf(blockers),
                blockers.isEmpty() ? CompositeState.DECOMMISSION_READY : CompositeState.LEGACY_DECOMMISSION_BLOCKED,
                blockers.isEmpty() ? List.of("DISABLE_TRAFFIC", "REVOKE_WRITE", "READ_ONLY_ARCHIVE", "STOP_RUNTIME") : List.of());
    }

    private void requireGate(boolean condition, String blocker, List<String> blockers) {
        if (!condition) blockers.add(blocker);
    }

    private CompositeState nextState(StepType type) {
        return switch (type) {
            case START_SYNC, WAIT_LAG, RUN_RECONCILIATION -> CompositeState.DATA_SYNCHRONIZING;
            case SHIFT_TRAFFIC -> CompositeState.SHADOW_VALIDATING;
            case SWITCH_READ -> CompositeState.READ_CUTOVER;
            case SWITCH_WRITE -> CompositeState.WRITE_CUTOVER;
            case HOLD -> CompositeState.STABILITY_HOLD;
            case DECOMMISSION -> CompositeState.DECOMMISSION_READY;
            case ROLLBACK -> CompositeState.ROLLBACK_REQUIRED;
            default -> CompositeState.COMPATIBILITY_PREPARING;
        };
    }

    private boolean allowedTransition(CompositeState current, CompositeState next) {
        if (next == CompositeState.ROLLBACK_REQUIRED || next == CompositeState.CUTOVER_PAUSED) return true;
        Map<CompositeState,Set<CompositeState>> allowed = new EnumMap<>(CompositeState.class);
        allowed.put(CompositeState.COMPATIBILITY_PREPARING, Set.of(CompositeState.DATA_SYNCHRONIZING, CompositeState.SHADOW_VALIDATING));
        allowed.put(CompositeState.DATA_SYNCHRONIZING, Set.of(CompositeState.DATA_SYNCHRONIZING, CompositeState.SHADOW_VALIDATING, CompositeState.READ_CUTOVER));
        allowed.put(CompositeState.SHADOW_VALIDATING, Set.of(CompositeState.DATA_SYNCHRONIZING, CompositeState.READ_CUTOVER));
        allowed.put(CompositeState.READ_CUTOVER, Set.of(CompositeState.WRITE_CUTOVER, CompositeState.SHADOW_VALIDATING));
        allowed.put(CompositeState.WRITE_CUTOVER, Set.of(CompositeState.FULL_TRAFFIC, CompositeState.STABILITY_HOLD));
        allowed.put(CompositeState.FULL_TRAFFIC, Set.of(CompositeState.STABILITY_HOLD));
        allowed.put(CompositeState.STABILITY_HOLD, Set.of(CompositeState.LEGACY_READ_ONLY, CompositeState.DECOMMISSION_READY));
        allowed.put(CompositeState.LEGACY_READ_ONLY, Set.of(CompositeState.DECOMMISSION_READY));
        return allowed.getOrDefault(current, Set.of()).contains(next);
    }
}
