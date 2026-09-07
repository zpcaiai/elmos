package io.elmos.roadmap;

import java.util.*;

import static io.elmos.roadmap.ProductRoadmapModels.*;

/** Independent, sequential and fail-closed evaluator. It never performs or approves external work. */
public final class ProductRoadmapGovernance {
    public EvaluationResult evaluate(EvaluationRequest request) {
        Objects.requireNonNull(request, "request");
        BatchDefinition definition = ProductRoadmapCatalog.require(request.batch());
        Map<String, List<GateEvidence>> byGate = new LinkedHashMap<>();
        request.evidence().forEach(value -> byGate.computeIfAbsent(value.gateId(), ignored -> new ArrayList<>()).add(value));
        List<String> blockers = new ArrayList<>();
        List<GateResult> results = new ArrayList<>();
        String highestGate = "BLOCKED";
        boolean sequenceOpen = true;

        Set<String> known = new HashSet<>(definition.gates().stream().map(GateDefinition::id).toList());
        for (String value : byGate.keySet()) if (!known.contains(value)) blockers.add("UNKNOWN_GATE:" + value);
        for (GateDefinition gate : definition.gates()) {
            List<GateEvidence> candidates = byGate.getOrDefault(gate.id(), List.of());
            List<String> reasons = new ArrayList<>();
            GateEvidence evidence = null;
            if (candidates.isEmpty()) reasons.add("EXTERNAL_EVIDENCE_NOT_RUN");
            else if (candidates.size() > 1) reasons.add("DUPLICATE_GATE_EVIDENCE");
            else evidence = candidates.getFirst();
            if (evidence != null) validate(request, evidence, reasons);
            boolean passed = reasons.isEmpty();
            if (sequenceOpen && passed) highestGate = gate.id(); else sequenceOpen = false;
            for (String reason : reasons) blockers.add(gate.id() + ":" + reason);
            results.add(new GateResult(gate.id(), evidence == null ? EvidenceStatus.NOT_RUN : evidence.status(), passed, reasons));
        }
        List<String> finalBlockers = blockers.stream().distinct().sorted().toList();
        boolean complete = results.stream().allMatch(GateResult::passed);
        Decision decision = complete && finalBlockers.isEmpty() ? Decision.READY_FOR_HUMAN_DECISION : Decision.BLOCKED;
        List<String> restrictions = List.of(
                "A_NAMED_HUMAN_MUST_REVIEW_AND_DECIDE",
                "NO_EXTERNAL_ACTION_IS_AUTHORIZED_BY_THIS_RESULT",
                "FINANCE_HR_SECURITY_AND_PRODUCTION_SYSTEMS_REMAIN_AUTHORITATIVE",
                "MISSING_OR_CONFLICTING_EVIDENCE_REMAINS_EXPLICIT");
        return new EvaluationResult(definition, request, decision, highestGate, complete,
                true, false, results, finalBlockers, restrictions, false);
    }

    private static void validate(EvaluationRequest request, GateEvidence value, List<String> reasons) {
        if (!value.organizationId().equals(request.organizationId())) reasons.add("TENANT_MISMATCH");
        if (!value.runId().equals(request.runId())) reasons.add("RUN_MISMATCH");
        if (!value.snapshotDigest().equals(request.snapshotDigest())) reasons.add("SNAPSHOT_MISMATCH");
        if (!value.policyVersion().equals(request.policyVersion())) reasons.add("POLICY_VERSION_MISMATCH");
        if (!value.independentJudge()) reasons.add("INDEPENDENT_JUDGE_REQUIRED");
        if (value.status() != EvidenceStatus.PASSED) reasons.add("STATUS_" + value.status());
        if (value.coverage() != 1.0) reasons.add("COVERAGE_INCOMPLETE");
        if (value.criticalOpenRisks() > 0) reasons.add("CRITICAL_RISK_OPEN");
        if (value.evidenceRefs().isEmpty()) reasons.add("IMMUTABLE_EVIDENCE_REF_REQUIRED");
        if (value.observedAt().isAfter(request.evaluatedAt())) reasons.add("FUTURE_DATED_EVIDENCE");
        if (value.externalOperationExecuted()) reasons.add("CONTROL_PLANE_EXECUTION_FORBIDDEN");
    }
}
