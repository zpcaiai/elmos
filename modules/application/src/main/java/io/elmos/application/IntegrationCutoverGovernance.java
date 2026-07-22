package io.elmos.application;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/** Independent judge; workers may submit evidence but cannot mutate this decision. */
public final class IntegrationCutoverGovernance {
    public enum Decision { PASS, FAIL, STALE, UNKNOWN }
    public record Evidence(
            String sourceArtifact, String evaluatedArtifact, boolean evidenceFresh,
            boolean contractValidated, boolean deliveryValidated, boolean businessResultValidated,
            boolean orderingValidated, boolean idempotencyValidated,
            boolean producerReady, boolean consumerReady, boolean partnerReady, boolean workflowReady,
            boolean backlogCleared, boolean dlqResolved, boolean lagWithinSlo, boolean unknownConsumersZero,
            boolean replayAuthorized, boolean bridgeReversible, boolean rollbackFeasible,
            boolean stabilityHoldSatisfied, boolean legacyProducerZero, boolean legacyConsumerZero,
            boolean legacyPartnerTrafficZero, boolean legacyWorkflowInstancesZero,
            boolean credentialsRevoked, boolean certificatesRevoked, boolean configArchived,
            List<String> evidenceRefs) {
        public Evidence { evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs); }
    }
    public record Result(Decision decision, List<String> blockers, List<String> unknowns, Instant decidedAt) {}

    public Result evaluateCutover(Evidence e, Instant now) {
        Objects.requireNonNull(e, "integration cutover evidence is required");
        List<String> blockers = new ArrayList<>();
        List<String> unknowns = new ArrayList<>();
        if (!e.evidenceFresh() || !same(e.sourceArtifact(), e.evaluatedArtifact())) blockers.add("INTEGRATION_EVIDENCE_STALE");
        if (!e.contractValidated()) blockers.add("CONTRACT_NOT_VALIDATED");
        if (!e.deliveryValidated()) blockers.add("DELIVERY_SEMANTICS_UNKNOWN");
        if (!e.businessResultValidated()) blockers.add("BUSINESS_RESULT_NOT_VALIDATED");
        if (!e.orderingValidated()) blockers.add("MESSAGE_ORDERING_RISK");
        if (!e.idempotencyValidated()) blockers.add("EFFECTIVELY_ONCE_NOT_VALIDATED");
        if (!e.producerReady()) blockers.add("PRODUCER_CUTOVER_BLOCKED");
        if (!e.consumerReady()) blockers.add("CONSUMER_CUTOVER_BLOCKED");
        if (!e.partnerReady()) blockers.add("PARTNER_CUTOVER_BLOCKED");
        if (!e.workflowReady()) blockers.add("WORKFLOW_CUTOVER_BLOCKED");
        if (!e.backlogCleared()) blockers.add("BACKLOG_NOT_CLEARED");
        if (!e.dlqResolved()) blockers.add("DLQ_NOT_RESOLVED");
        if (!e.lagWithinSlo()) blockers.add("CONSUMER_LAG_EXCEEDED");
        if (!e.unknownConsumersZero()) blockers.add("UNKNOWN_CONSUMER");
        if (!e.replayAuthorized()) blockers.add("MESSAGE_REPLAY_NOT_AUTHORIZED");
        if (!e.bridgeReversible()) blockers.add("BRIDGE_NOT_REVERSIBLE");
        if (!e.rollbackFeasible()) blockers.add("ROLLBACK_BLOCKED");
        if (e.evidenceRefs().isEmpty()) unknowns.add("INTEGRATION_EVIDENCE_MISSING");
        Decision decision = blockers.contains("INTEGRATION_EVIDENCE_STALE") ? Decision.STALE
                : !blockers.isEmpty() ? Decision.FAIL : !unknowns.isEmpty() ? Decision.UNKNOWN : Decision.PASS;
        return new Result(decision, List.copyOf(blockers), List.copyOf(unknowns), now);
    }

    public Result evaluateDecommission(Evidence e, Instant now) {
        Result cutover = evaluateCutover(e, now);
        List<String> blockers = new ArrayList<>(cutover.blockers());
        List<String> unknowns = new ArrayList<>(cutover.unknowns());
        if (!e.stabilityHoldSatisfied()) blockers.add("STABILITY_HOLD_INCOMPLETE");
        if (!e.legacyProducerZero()) blockers.add("LEGACY_PRODUCER_REMAINS");
        if (!e.legacyConsumerZero()) blockers.add("LEGACY_CONSUMER_REMAINS");
        if (!e.legacyPartnerTrafficZero()) blockers.add("LEGACY_PARTNER_TRAFFIC_REMAINS");
        if (!e.legacyWorkflowInstancesZero()) blockers.add("LEGACY_WORKFLOW_INSTANCE_REMAINS");
        if (!e.credentialsRevoked()) blockers.add("INTEGRATION_CREDENTIAL_REMAINS");
        if (!e.certificatesRevoked()) blockers.add("PARTNER_CERTIFICATE_REMAINS");
        if (!e.configArchived()) blockers.add("LEGACY_CONFIG_NOT_ARCHIVED");
        Decision decision = blockers.contains("INTEGRATION_EVIDENCE_STALE") ? Decision.STALE
                : !blockers.isEmpty() ? Decision.FAIL : !unknowns.isEmpty() ? Decision.UNKNOWN : Decision.PASS;
        return new Result(decision, List.copyOf(blockers), List.copyOf(unknowns), now);
    }

    private static boolean same(String left, String right) {
        return left != null && !left.isBlank() && left.equals(right);
    }
}
