package io.elmos.migrationpack;

import java.util.*;

import static io.elmos.migrationpack.MigrationPackModels.*;

/** Prepares evidence for the package script gate. This class is intentionally not a certification gate. */
public final class MigrationPackAdmissionService {
    public AdmissionResult evaluate(AdmissionRequest request) {
        Objects.requireNonNull(request, "request");
        PackDefinition definition = MigrationPackCatalog.require(request.pack());
        Map<String, List<PhaseEvidence>> byPhase = new LinkedHashMap<>();
        request.evidence().forEach(value -> byPhase.computeIfAbsent(value.phase(), ignored -> new ArrayList<>()).add(value));
        List<String> blockers = new ArrayList<>();
        Set<String> expected = Set.copyOf(definition.requiredPhases());
        for (String value : byPhase.keySet()) if (!expected.contains(value)) blockers.add("UNKNOWN_PHASE:" + value);
        for (String phase : definition.requiredPhases()) {
            List<PhaseEvidence> values = byPhase.getOrDefault(phase, List.of());
            if (values.isEmpty()) { blockers.add(phase + ":NOT_RUN"); continue; }
            if (values.size() > 1) { blockers.add(phase + ":DUPLICATE_EVIDENCE"); continue; }
            validate(request, phase, values.getFirst(), blockers);
        }
        List<String> finalBlockers = blockers.stream().distinct().sorted().toList();
        boolean complete = finalBlockers.isEmpty() && byPhase.keySet().equals(expected);
        AdmissionDecision decision = complete ? AdmissionDecision.READY_FOR_PACK_GATE : AdmissionDecision.BLOCKED;
        List<String> restrictions = List.of(
                "ONLY_" + definition.gateCommand() + "_MAY_DECIDE_CERTIFICATION_READINESS",
                "THIS_API_DOES_NOT_CERTIFY_A_ROUTE_PACK_OR_PORTFOLIO",
                "PRODUCTION_WRITES_AND_PERMISSION_BROADENING_ARE_FORBIDDEN",
                "UNSUPPORTED_AND_INACCESSIBLE_CASES_REMAIN_IN_METRICS");
        return new AdmissionResult(definition, request, decision, complete, finalBlockers, restrictions,
                definition.gateCommand(), false, false);
    }

    private static void validate(AdmissionRequest request, String phase, PhaseEvidence value, List<String> blockers) {
        String prefix = phase + ":";
        if (!value.organizationId().equals(request.organizationId())) blockers.add(prefix + "TENANT_MISMATCH");
        if (!value.assessmentId().equals(request.assessmentId())) blockers.add(prefix + "ASSESSMENT_MISMATCH");
        if (!value.sourceSnapshotDigest().equals(request.sourceSnapshotDigest())) blockers.add(prefix + "SOURCE_SNAPSHOT_MISMATCH");
        if (!value.targetSnapshotDigest().equals(request.targetSnapshotDigest())) blockers.add(prefix + "TARGET_SNAPSHOT_MISMATCH");
        if (!value.packVersion().equals(request.packVersion())) blockers.add(prefix + "PACK_VERSION_MISMATCH");
        if (value.status() != EvidenceStatus.PASSED) blockers.add(prefix + "STATUS_" + value.status());
        if (!value.independentJudge()) blockers.add(prefix + "INDEPENDENT_JUDGE_REQUIRED");
        if (!value.realEnvironment()) blockers.add(prefix + "REAL_ENVIRONMENT_REQUIRED");
        if (!value.defaultDenyNetworkPassed()) blockers.add(prefix + "DEFAULT_DENY_NETWORK_REQUIRED");
        if (!value.idempotencyPassed()) blockers.add(prefix + "IDEMPOTENCY_REQUIRED");
        if (!value.semanticIntegrityPassed()) blockers.add(prefix + "SEMANTIC_INTEGRITY_REQUIRED");
        if (value.unsupportedCount() > 0) blockers.add(prefix + "UNSUPPORTED_SEMANTICS_PRESENT");
        if (value.criticalOpenRisks() > 0) blockers.add(prefix + "CRITICAL_RISK_OPEN");
        if (value.evidenceRefs().isEmpty()) blockers.add(prefix + "IMMUTABLE_EVIDENCE_REF_REQUIRED");
        if (value.observedAt().isAfter(request.evaluatedAt())) blockers.add(prefix + "FUTURE_DATED_EVIDENCE");
        if (value.productionMutationExecuted()) blockers.add(prefix + "PRODUCTION_MUTATION_FORBIDDEN");
    }
}
