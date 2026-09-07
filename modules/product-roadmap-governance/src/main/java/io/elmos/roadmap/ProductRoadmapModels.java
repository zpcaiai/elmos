package io.elmos.roadmap;

import java.time.Instant;
import java.util.*;

/** Evidence-bound contracts for the ELMOS commercial product roadmap, Batches 27-34. */
public final class ProductRoadmapModels {
    private ProductRoadmapModels() {}

    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, INCONCLUSIVE, BLOCKED }
    public enum Decision { BLOCKED, READY_FOR_HUMAN_DECISION }

    public record GateDefinition(String id, String label) {
        public GateDefinition { text(id, "id"); text(label, "label"); }
    }

    public record BatchDefinition(int batch, String title, String contractVersion,
                                  int runtimeSkillCount, int acceptanceScenarioCount,
                                  List<GateDefinition> gates, List<String> prohibitedActions) {
        public BatchDefinition {
            if (batch < 27 || batch > 34) throw new IllegalArgumentException("product batch must be 27-34");
            text(title, "title"); text(contractVersion, "contractVersion");
            if (runtimeSkillCount < 0 || acceptanceScenarioCount < 0)
                throw new IllegalArgumentException("counts must be non-negative");
            gates = nonempty(gates, "gates"); prohibitedActions = nonempty(prohibitedActions, "prohibitedActions");
            if (new HashSet<>(gates.stream().map(GateDefinition::id).toList()).size() != gates.size())
                throw new IllegalArgumentException("gate IDs must be unique");
        }
        public String finalGate() { return gates.getLast().id(); }
    }

    public record GateEvidence(String gateId, EvidenceStatus status, String organizationId,
                               String runId, String snapshotDigest, String policyVersion,
                               String authorityId, boolean independentJudge, double coverage,
                               int criticalOpenRisks, Instant observedAt, List<String> evidenceRefs,
                               boolean externalOperationExecuted) {
        public GateEvidence {
            text(gateId, "gateId"); required(status, "status"); text(organizationId, "organizationId");
            text(runId, "runId"); digest(snapshotDigest, "snapshotDigest"); text(policyVersion, "policyVersion");
            text(authorityId, "authorityId"); required(observedAt, "observedAt");
            if (!Double.isFinite(coverage) || coverage < 0 || coverage > 1)
                throw new IllegalArgumentException("coverage must be between zero and one");
            if (criticalOpenRisks < 0) throw new IllegalArgumentException("criticalOpenRisks must be non-negative");
            evidenceRefs = copy(evidenceRefs);
            if (externalOperationExecuted)
                throw new IllegalArgumentException("product governance evidence cannot claim control-plane execution");
        }
    }

    public record EvaluationRequest(int batch, String organizationId, String runId,
                                    String snapshotDigest, String policyVersion, String humanOwnerId,
                                    Instant evaluatedAt, List<GateEvidence> evidence) {
        public EvaluationRequest {
            if (batch < 27 || batch > 34) throw new IllegalArgumentException("product batch must be 27-34");
            text(organizationId, "organizationId"); text(runId, "runId"); digest(snapshotDigest, "snapshotDigest");
            text(policyVersion, "policyVersion"); text(humanOwnerId, "humanOwnerId");
            required(evaluatedAt, "evaluatedAt"); evidence = copy(evidence);
        }
    }

    public record GateResult(String gateId, EvidenceStatus status, boolean passed, List<String> reasons) {
        public GateResult { text(gateId, "gateId"); required(status, "status"); reasons = copy(reasons); }
    }

    public record EvaluationResult(BatchDefinition definition, EvaluationRequest request,
                                   Decision decision, String highestGate, boolean evidenceComplete,
                                   boolean humanApprovalRequired, boolean humanApprovalGranted,
                                   List<GateResult> gates, List<String> blockers, List<String> restrictions,
                                   boolean externalOperationExecuted) {
        public EvaluationResult {
            required(definition, "definition"); required(request, "request"); required(decision, "decision");
            text(highestGate, "highestGate"); gates = nonempty(gates, "gates");
            blockers = copy(blockers); restrictions = nonempty(restrictions, "restrictions");
            if (!humanApprovalRequired || humanApprovalGranted || externalOperationExecuted)
                throw new IllegalArgumentException("roadmap evaluation may only prepare an ungranted human decision");
            if (decision == Decision.READY_FOR_HUMAN_DECISION
                    && (!evidenceComplete || !blockers.isEmpty() || !highestGate.equals(definition.finalGate())))
                throw new IllegalArgumentException("ready decision requires complete final-gate evidence");
        }
    }

    static void text(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static void digest(String value, String field) {
        text(value, field);
        if (!value.matches("[a-f0-9]{64}")) throw new IllegalArgumentException(field + " must be a lowercase SHA-256 digest");
    }
    static <T> T required(T value, String field) {
        if (value == null) throw new IllegalArgumentException(field + " is required"); return value;
    }
    static <T> List<T> copy(List<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static <T> List<T> nonempty(List<T> values, String field) {
        if (values == null || values.isEmpty() || values.stream().anyMatch(Objects::isNull))
            throw new IllegalArgumentException(field + " must not be empty");
        return List.copyOf(values);
    }
}
