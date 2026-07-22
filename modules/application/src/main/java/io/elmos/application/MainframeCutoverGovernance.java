package io.elmos.application;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/** Independent Batch 19 cutover/decommission decision kernel; it cannot submit jobs or mutate routes. */
public final class MainframeCutoverGovernance {
    public enum Decision { PASS, FAIL, INCONCLUSIVE, STALE }
    public record Evidence(String sourceArtifact, String evaluatedArtifact,
                           boolean sourceRuntimeCorrelated, boolean copybooksResolved,
                           boolean jclAndSchedulerComplete, boolean onlineTransactionsValidated,
                           boolean batchJobsValidated, boolean semanticEquivalent,
                           boolean shadowSideEffectsControlled, boolean dataAuthorityUnique,
                           boolean rollbackFeasible, boolean stabilityHoldComplete,
                           boolean runtimeUsageZero, boolean externalConsumersZero,
                           boolean racfAndCredentialsRevoked, boolean evidenceFresh,
                           List<String> evidenceRefs) {
        public Evidence { evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs); }
    }
    public record Result(Decision decision, List<String> blockers, List<String> unknowns,
                         boolean cutoverAuthorized, boolean decommissionAuthorized,
                         boolean workerModifiedRoute, Instant evaluatedAt, List<String> evidenceRefs) {}

    public Result evaluateCutover(Evidence e, Instant now) {
        if (e == null) throw new IllegalArgumentException("mainframe cutover evidence is required");
        var blockers = new ArrayList<String>();
        var unknowns = new ArrayList<String>();
        if (!e.evidenceFresh() || !same(e.sourceArtifact(), e.evaluatedArtifact())) blockers.add("MAINFRAME_EVIDENCE_STALE");
        if (!e.sourceRuntimeCorrelated()) blockers.add("RUNTIME_SOURCE_MISMATCH");
        if (!e.copybooksResolved()) blockers.add("COPYBOOK_VERSION_AMBIGUOUS");
        if (!e.jclAndSchedulerComplete()) blockers.add("JCL_FLOW_INCOMPLETE");
        if (!e.onlineTransactionsValidated()) blockers.add("ONLINE_TRANSACTION_GATE_FAILED");
        if (!e.batchJobsValidated()) blockers.add("BATCH_GATE_FAILED");
        if (!e.semanticEquivalent()) blockers.add("TRANSFORMATION_NOT_EQUIVALENT");
        if (!e.shadowSideEffectsControlled()) blockers.add("SHADOW_SIDE_EFFECT_UNCONTROLLED");
        if (!e.dataAuthorityUnique()) blockers.add("MULTIPLE_DATA_WRITERS");
        if (!e.rollbackFeasible()) blockers.add("ROLLBACK_BLOCKED");
        if (e.evidenceRefs().isEmpty()) unknowns.add("MAINFRAME_EVIDENCE_MISSING");
        Decision decision = decide(blockers, unknowns);
        return new Result(decision, List.copyOf(blockers), List.copyOf(unknowns), decision == Decision.PASS, false,
                false, now, e.evidenceRefs());
    }

    public Result evaluateDecommission(Evidence e, Instant now) {
        Result cutover = evaluateCutover(e, now);
        var blockers = new ArrayList<>(cutover.blockers());
        var unknowns = new ArrayList<>(cutover.unknowns());
        if (!e.stabilityHoldComplete()) blockers.add("STABILITY_HOLD_INCOMPLETE");
        if (!e.runtimeUsageZero()) blockers.add("LEGACY_USAGE_REMAINS");
        if (!e.externalConsumersZero()) blockers.add("UNKNOWN_EXTERNAL_CONSUMER");
        if (!e.racfAndCredentialsRevoked()) blockers.add("MAINFRAME_ACCESS_REMAINS");
        Decision decision = decide(blockers, unknowns);
        return new Result(decision, List.copyOf(blockers), List.copyOf(unknowns), cutover.cutoverAuthorized(), decision == Decision.PASS,
                false, now, e.evidenceRefs());
    }
    private static Decision decide(List<String> blockers, List<String> unknowns) {
        return blockers.contains("MAINFRAME_EVIDENCE_STALE") ? Decision.STALE
                : !blockers.isEmpty() ? Decision.FAIL : !unknowns.isEmpty() ? Decision.INCONCLUSIVE : Decision.PASS;
    }
    private static boolean same(String a, String b) { return a != null && !a.isBlank() && a.equals(b); }
}
