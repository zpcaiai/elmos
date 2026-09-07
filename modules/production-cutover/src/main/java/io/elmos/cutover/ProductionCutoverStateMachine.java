package io.elmos.cutover;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import static io.elmos.cutover.ProductionCutoverModels.*;

/** Authorizes, but deliberately does not execute, forward and rollback production transitions. */
public final class ProductionCutoverStateMachine {
    public enum TransitionKind { FORWARD, ROLLBACK, NOOP, BLOCKED }
    public record TransitionDecision(Phase from, Phase to, TransitionKind kind, Gate requiredGate,
                                     boolean authorized, boolean productionChangeExecuted,
                                     List<String> blockers) {
        public TransitionDecision {
            blockers = List.copyOf(blockers);
            if (productionChangeExecuted) throw new IllegalArgumentException("policy state machine cannot execute production changes");
        }
    }

    public TransitionDecision authorize(Outcome outcome, Phase to) {
        Objects.requireNonNull(outcome, "outcome"); Objects.requireNonNull(to, "to");
        Phase from = outcome.request().currentPhase();
        if (from == to) return new TransitionDecision(from, to, TransitionKind.NOOP,
                minimumEvidenceForObservedPhase(from), true, false, List.of());
        List<String> blockers = new ArrayList<>();
        if (to.sequence() == from.sequence() + 1) {
            Gate required = requiredToEnter(to);
            if (outcome.report().gate().level() < required.level()) blockers.add("required cutover gate has not passed");
            if (!outcome.report().blockers().isEmpty()) blockers.add("conformance report has blocking evidence");
            return new TransitionDecision(from, to, blockers.isEmpty() ? TransitionKind.FORWARD : TransitionKind.BLOCKED,
                    required, blockers.isEmpty(), false, blockers);
        }
        if (to.sequence() < from.sequence()) {
            RollbackIncidentEvidence rollback = outcome.rollback();
            TrafficAuthorityEvidence traffic = outcome.traffic();
            if (from == Phase.P12_DECOMMISSIONED) blockers.add("decommissioned legacy cannot be traffic-rolled back");
            if (rollback == null || !rollback.currentPhaseReversible() || !rollback.reverseSyncWithinThreshold())
                blockers.add("current rollback evidence is insufficient");
            if (traffic == null || !traffic.sourceFallbackCapacitySufficient() || !traffic.rollbackPointVerified())
                blockers.add("source capacity or rollback point is not verified");
            if (traffic != null && traffic.irreversibilityFrontierCrossed()) blockers.add("irreversibility frontier requires forward-fix");
            return new TransitionDecision(from, to, blockers.isEmpty() ? TransitionKind.ROLLBACK : TransitionKind.BLOCKED,
                    Gate.BLOCKED, blockers.isEmpty(), false, blockers);
        }
        blockers.add("phase skipping is prohibited");
        return new TransitionDecision(from, to, TransitionKind.BLOCKED, requiredToEnter(to), false, false, blockers);
    }

    static Gate minimumEvidenceForObservedPhase(Phase phase) {
        return switch (phase) {
            case P0_PREPARED -> Gate.BLOCKED;
            case P1_SCHEMA_EXPANDED, P2_BACKFILL_RUNNING, P3_INCREMENTAL_SYNC_HEALTHY, P4_SHADOW_READ -> Gate.C_A;
            case P5_READ_CANARY, P6_TARGET_READ_PRIMARY -> Gate.C_B;
            case P7_WRITE_CANARY -> Gate.C_C;
            case P8_TARGET_WRITE_PRIMARY -> Gate.C_D;
            case P9_SOURCE_READ_ONLY, P10_HYPERCARE -> Gate.C_E;
            case P11_RETIREMENT_CANDIDATE -> Gate.C_F;
            case P12_DECOMMISSIONED -> Gate.C_G;
        };
    }

    private static Gate requiredToEnter(Phase phase) {
        if (phase == Phase.P12_DECOMMISSIONED) return Gate.C_F;
        return minimumEvidenceForObservedPhase(phase);
    }
}
