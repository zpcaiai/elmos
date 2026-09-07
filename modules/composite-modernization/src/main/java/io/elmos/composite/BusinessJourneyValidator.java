package io.elmos.composite;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class BusinessJourneyValidator {
    public record JourneyStep(String stepId, String systemNodeId, Language language,
                              String inputContract, String outputContract,
                              List<String> expectedSideEffects, long timeoutMs,
                              boolean modelStep) {
        public JourneyStep {
            require(stepId, "stepId"); require(systemNodeId, "systemNodeId");
            Objects.requireNonNull(language); require(inputContract, "inputContract");
            require(outputContract, "outputContract"); expectedSideEffects = immutable(expectedSideEffects);
            if (timeoutMs < 1) throw new IllegalArgumentException("timeoutMs must be positive");
        }
    }
    public record Journey(String journeyId, String organizationId, List<JourneyStep> steps,
                          boolean critical, List<String> evidenceRefs) {
        public Journey {
            require(journeyId, "journeyId"); require(organizationId, "organizationId");
            steps = immutable(steps); evidenceRefs = immutable(evidenceRefs);
            if (steps.isEmpty()) throw new IllegalArgumentException("journey requires steps");
        }
    }
    public record JourneyRunEvidence(boolean allServiceChecksPassed, boolean contractsPassed,
                                     boolean finalBusinessStatePassed, int expectedMessages,
                                     List<String> observedMessageIds, boolean messageOrderingPassed,
                                     boolean modelContractPassed, boolean traceContinuous,
                                     boolean sloPassed, boolean compensationsPassed,
                                     boolean syntheticDataCleaned, List<String> evidenceRefs) {
        public JourneyRunEvidence {
            observedMessageIds = immutable(observedMessageIds); evidenceRefs = immutable(evidenceRefs);
        }
    }
    public record JourneyDecision(ConsistencyStatus status, List<String> blockers,
                                  double stepCoverage, boolean systemGatePassed) {}

    public JourneyDecision validate(Journey journey, JourneyRunEvidence evidence) {
        ArrayList<String> blockers = new ArrayList<>();
        if (!evidence.allServiceChecksPassed()) blockers.add("SERVICE_CHECK_FAILED");
        if (!evidence.contractsPassed()) blockers.add("CROSS_CONTRACT_FAILED");
        if (!evidence.finalBusinessStatePassed()) blockers.add("BUSINESS_INVARIANT_FAILED");
        Set<String> unique = new HashSet<>(evidence.observedMessageIds());
        if (unique.size() != evidence.observedMessageIds().size()) blockers.add("DUPLICATE_MESSAGE_DETECTED");
        if (unique.size() < evidence.expectedMessages()) blockers.add("MESSAGE_MISSING");
        if (!evidence.messageOrderingPassed()) blockers.add("MESSAGE_ORDERING_FAILED");
        if (journey.steps().stream().anyMatch(JourneyStep::modelStep) && !evidence.modelContractPassed()) {
            blockers.add("MODEL_CONTRACT_FAILED");
        }
        if (!evidence.traceContinuous()) blockers.add("TRACE_CONTINUITY_BROKEN");
        if (!evidence.sloPassed()) blockers.add("SYSTEM_SLO_FAILED");
        if (!evidence.compensationsPassed()) blockers.add("SAGA_COMPENSATION_FAILED");
        if (!evidence.syntheticDataCleaned()) blockers.add("SYNTHETIC_DATA_CLEANUP_INCOMPLETE");
        if (journey.evidenceRefs().isEmpty() || evidence.evidenceRefs().isEmpty()) blockers.add("JOURNEY_EVIDENCE_MISSING");
        ConsistencyStatus status;
        if (blockers.contains("BUSINESS_INVARIANT_FAILED")) status = ConsistencyStatus.BUSINESS_INVARIANT_FAILED;
        else if (blockers.stream().anyMatch(item -> item.contains("MESSAGE"))) status = ConsistencyStatus.MESSAGE_INCOMPLETE;
        else if (!blockers.isEmpty()) status = ConsistencyStatus.INCONCLUSIVE;
        else status = ConsistencyStatus.CONSISTENT;
        double coverage = evidence.allServiceChecksPassed() ? 1 : 0;
        return new JourneyDecision(status, List.copyOf(blockers), coverage, blockers.isEmpty());
    }
}
