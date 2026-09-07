package io.elmos.application;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Batch 16 control-plane authority. It adjudicates evidence and never calls a provider. */
public final class InfrastructureCutoverGovernance {
    public enum Stage {
        DISCOVERY, SHADOW_RUNNING, CANARY_RUNNING, TRAFFIC_CUTOVER,
        STABILITY_HOLD, LEGACY_STANDBY, DECOMMISSION_READY, DECOMMISSIONED
    }
    public enum Decision { ADVANCE, HOLD, HUMAN_REVIEW, BLOCKED }

    public record Evidence(
            String organizationId,
            Stage currentStage,
            Stage requestedStage,
            boolean freezeManifestPassed,
            boolean targetValidationPassed,
            boolean planPolicySecurityPassed,
            boolean supplyChainPassed,
            boolean networkEnforcementPassed,
            boolean observabilityPassed,
            boolean sloPassed,
            boolean costPassed,
            boolean resiliencePassed,
            boolean restorePassed,
            boolean portabilityPassed,
            boolean stateSynchronizationPassed,
            boolean rollbackPassed,
            boolean trafficAndConsumerGatePassed,
            boolean decommissionCleanupPassed,
            List<String> evidenceRefs,
            String approvedBy) {
        public Evidence {
            require(organizationId, "organizationId");
            Objects.requireNonNull(currentStage); Objects.requireNonNull(requestedStage);
            evidenceRefs = List.copyOf(Objects.requireNonNull(evidenceRefs));
        }
    }

    public record Result(Decision decision, boolean automatic, List<String> blockers,
                         List<String> evidenceRefs, Map<String, String> checks) {}

    public Result evaluate(Evidence evidence) {
        if (evidence.requestedStage().ordinal() != evidence.currentStage().ordinal() + 1) {
            return result(Decision.BLOCKED, false, List.of("INFRASTRUCTURE_STAGE_SKIP"), evidence, Map.of());
        }
        if (evidence.evidenceRefs().isEmpty()) {
            return result(Decision.HOLD, false, List.of("INFRASTRUCTURE_EVIDENCE_MISSING"), evidence, Map.of());
        }
        var checks = new LinkedHashMap<String, String>();
        var blockers = new ArrayList<String>();
        gate(checks, blockers, "FREEZE_MANIFEST", evidence.freezeManifestPassed());
        gate(checks, blockers, "TARGET_VALIDATION", evidence.targetValidationPassed());
        gate(checks, blockers, "PLAN_POLICY_SECURITY", evidence.planPolicySecurityPassed());
        gate(checks, blockers, "CONTAINER_SUPPLY_CHAIN", evidence.supplyChainPassed());
        gate(checks, blockers, "NETWORK_ENFORCEMENT", evidence.networkEnforcementPassed());
        gate(checks, blockers, "OBSERVABILITY", evidence.observabilityPassed());
        if (atOrAfter(evidence.requestedStage(), Stage.CANARY_RUNNING)) {
            gate(checks, blockers, "SLO", evidence.sloPassed());
            gate(checks, blockers, "COST", evidence.costPassed());
            gate(checks, blockers, "STATE_SYNCHRONIZATION", evidence.stateSynchronizationPassed());
        }
        if (atOrAfter(evidence.requestedStage(), Stage.TRAFFIC_CUTOVER)) {
            gate(checks, blockers, "RESILIENCE", evidence.resiliencePassed());
            gate(checks, blockers, "RESTORE", evidence.restorePassed());
            gate(checks, blockers, "PORTABILITY", evidence.portabilityPassed());
            gate(checks, blockers, "ROLLBACK", evidence.rollbackPassed());
        }
        if (atOrAfter(evidence.requestedStage(), Stage.LEGACY_STANDBY)) {
            gate(checks, blockers, "TRAFFIC_AND_UNKNOWN_CONSUMERS", evidence.trafficAndConsumerGatePassed());
        }
        if (atOrAfter(evidence.requestedStage(), Stage.DECOMMISSIONED)) {
            gate(checks, blockers, "DECOMMISSION_CLEANUP", evidence.decommissionCleanupPassed());
        }
        if (!blockers.isEmpty()) return result(Decision.HOLD, false, blockers, evidence, checks);
        if (requiresNamedApproval(evidence.requestedStage())
                && (evidence.approvedBy() == null || evidence.approvedBy().isBlank())) {
            return result(Decision.HUMAN_REVIEW, false,
                    List.of("NAMED_INFRASTRUCTURE_AUTHORITY_APPROVAL_REQUIRED"), evidence, checks);
        }
        return result(Decision.ADVANCE, evidence.requestedStage().ordinal() < Stage.TRAFFIC_CUTOVER.ordinal(),
                List.of(), evidence, checks);
    }

    private boolean requiresNamedApproval(Stage stage) {
        return stage == Stage.TRAFFIC_CUTOVER || stage == Stage.STABILITY_HOLD
                || stage == Stage.LEGACY_STANDBY || stage == Stage.DECOMMISSION_READY
                || stage == Stage.DECOMMISSIONED;
    }

    private boolean atOrAfter(Stage value, Stage threshold) {
        return value.ordinal() >= threshold.ordinal();
    }

    private void gate(Map<String, String> checks, List<String> blockers, String name, boolean passed) {
        checks.put(name, passed ? "PASS" : "FAIL");
        if (!passed) blockers.add(name + "_FAILED");
    }

    private Result result(Decision decision, boolean automatic, List<String> blockers,
                          Evidence evidence, Map<String, String> checks) {
        return new Result(decision, automatic, List.copyOf(blockers), evidence.evidenceRefs(), Map.copyOf(checks));
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
