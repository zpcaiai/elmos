package io.elmos.composite;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import static io.elmos.composite.CompositeModels.*;

public final class ProgressiveTrafficController {
    public enum Provider { KUBERNETES_GATEWAY, SERVICE_MESH, API_GATEWAY, LOAD_BALANCER,
        DNS, FEATURE_FLAG, APPLICATION_ROUTER, MESSAGE_ROUTER }
    public enum Stage { SHADOW_ONLY, CANARY_INTERNAL, CANARY_1, CANARY_5, CANARY_10,
        CANARY_25, CANARY_50, FULL_TRAFFIC }
    public enum Cohort { INTERNAL_USER, TEST_TENANT, LOW_RISK_TENANT, REGION,
        EMPLOYEE, RANDOM_PERCENTAGE, EXPLICIT_ALLOWLIST }

    public record GateEvidence(boolean providerHealthy, boolean availabilityPassed,
                               boolean errorRatePassed, boolean latencyPassed,
                               boolean businessInvariantPassed, boolean dataConsistencyPassed,
                               boolean contractPassed, boolean securityPassed,
                               boolean messageLagPassed, boolean cdcLagPassed,
                               boolean retryIdempotencyPassed, boolean sessionCompatible,
                               boolean unknownConsumersPresent, boolean rollbackVerified,
                               boolean writeOwnershipChange, boolean irreversibleOperation,
                               List<String> evidenceRefs) {
        public GateEvidence { evidenceRefs = immutable(evidenceRefs); }
    }
    public record TrafficStageRequest(Provider provider, Stage currentStage, Stage requestedStage,
                                      Cohort cohort, GateEvidence gates, boolean humanApproved) {}
    public record PromotionDecision(TrafficDecision decision, Stage effectiveStage,
                                    List<String> blockers, boolean automatic) {}

    public PromotionDecision evaluate(TrafficStageRequest request) {
        Objects.requireNonNull(request.provider()); Objects.requireNonNull(request.currentStage());
        Objects.requireNonNull(request.requestedStage()); Objects.requireNonNull(request.cohort());
        Objects.requireNonNull(request.gates());
        ArrayList<String> blockers = new ArrayList<>(); GateEvidence gate = request.gates();
        if (request.requestedStage().ordinal() != request.currentStage().ordinal() + 1) {
            blockers.add("TRAFFIC_STAGE_SKIP_OR_REPLAY_FORBIDDEN");
        }
        if (!gate.providerHealthy()) blockers.add("TRAFFIC_PROVIDER_UNAVAILABLE");
        if (!gate.availabilityPassed()) blockers.add("AVAILABILITY_GATE_FAILED");
        if (!gate.errorRatePassed()) blockers.add("ERROR_RATE_GATE_FAILED");
        if (!gate.latencyPassed()) blockers.add("LATENCY_GATE_FAILED");
        if (!gate.businessInvariantPassed()) blockers.add("BUSINESS_INVARIANT_FAILED");
        if (!gate.dataConsistencyPassed()) blockers.add("DATA_CONSISTENCY_FAILED");
        if (!gate.contractPassed()) blockers.add("CONTRACT_GATE_FAILED");
        if (!gate.securityPassed()) blockers.add("SECURITY_GATE_FAILED");
        if (!gate.messageLagPassed()) blockers.add("MESSAGE_LAG_GATE_FAILED");
        if (!gate.cdcLagPassed()) blockers.add("CDC_LAG_GATE_FAILED");
        if (!gate.retryIdempotencyPassed()) blockers.add("RETRY_IDEMPOTENCY_FAILED");
        if (!gate.sessionCompatible()) blockers.add("SESSION_COMPATIBILITY_FAILED");
        if (gate.unknownConsumersPresent()) blockers.add("UNKNOWN_CONSUMER_BLOCKER");
        if (!gate.rollbackVerified()) blockers.add("ROLLBACK_NOT_VERIFIED");
        if (gate.evidenceRefs().isEmpty()) blockers.add("CANARY_EVIDENCE_MISSING");
        boolean requiresHuman = gate.writeOwnershipChange() || gate.irreversibleOperation()
                || request.requestedStage() == Stage.FULL_TRAFFIC;
        if (requiresHuman && !request.humanApproved()) blockers.add("HUMAN_APPROVAL_REQUIRED");
        TrafficDecision decision;
        if (!gate.businessInvariantPassed()) decision = gate.writeOwnershipChange()
                ? TrafficDecision.HOLD : TrafficDecision.ROLLBACK;
        else if (!gate.providerHealthy()) decision = TrafficDecision.PAUSE;
        else if (!blockers.isEmpty()) decision = requiresHuman ? TrafficDecision.HUMAN_REVIEW : TrafficDecision.HOLD;
        else decision = TrafficDecision.PROMOTE;
        return new PromotionDecision(decision,
                decision == TrafficDecision.PROMOTE ? request.requestedStage() : request.currentStage(),
                List.copyOf(blockers), decision == TrafficDecision.PROMOTE && !requiresHuman);
    }
}
