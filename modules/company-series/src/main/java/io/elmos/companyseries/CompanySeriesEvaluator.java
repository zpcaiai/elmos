package io.elmos.companyseries;

import java.util.*;

import static io.elmos.companyseries.CompanySeriesModels.*;

/** Sequential, non-compensating and fail-closed evaluator over read-only external evidence. */
public final class CompanySeriesEvaluator {
    public Outcome evaluate(ProgramDefinition definition, Request request, AuthorityRegistry registry) {
        Objects.requireNonNull(definition, "definition"); Objects.requireNonNull(request, "request");
        Objects.requireNonNull(registry, "registry");
        Map<String, GateEvidence> observed = new LinkedHashMap<>();
        List<String> blockers = new ArrayList<>();
        List<String> refs = new ArrayList<>();
        String highestGate = "BLOCKED";
        boolean sequenceOpen = true;

        for (GateDefinition gate : definition.gates()) {
            GateEvidence evidence = observe(request, registry.authorityFor(gate.id()), gate, blockers);
            if (evidence != null) {
                observed.put(gate.id(), evidence);
                refs.addAll(evidence.evidenceRefs());
            }
            boolean passed = valid(definition, request, gate, evidence, blockers);
            if (sequenceOpen && passed) highestGate = gate.id();
            else sequenceOpen = false;
        }

        blockers = blockers.stream().distinct().sorted().toList();
        boolean complete = observed.size() == definition.gates().size()
                && definition.gates().stream().allMatch(gate -> passes(observed.get(gate.id())));
        boolean ready = complete && blockers.isEmpty() && highestGate.equals(definition.finalGate());
        String status = ready ? definition.finalStatus() : highestGate.equals("BLOCKED") ? "BLOCKED" : "PARTIAL";
        ConformanceReport report = new ConformanceReport(
                definition.batch(), definition.model(), request.programId(), request.sourceVersion(),
                request.organizationId(), highestGate, status, ready, complete,
                ready ? definition.dimensions() : List.of(), blockers, restrictions(definition),
                request.observedAt(), refs.stream().distinct().sorted().toList(), false);
        return new Outcome(definition, request, observed, report);
    }

    private static GateEvidence observe(Request request, EvidenceAuthority authority,
                                        GateDefinition gate, List<String> blockers) {
        if (authority == null) {
            blockers.add(gate.id() + " external authority is NOT_RUN");
            return null;
        }
        try {
            GateEvidence value = authority.observe(request, gate);
            if (value == null) blockers.add(gate.id() + " external evidence is NOT_RUN");
            return value;
        } catch (RuntimeException error) {
            blockers.add(gate.id() + " authority failed safely: " + error.getClass().getSimpleName());
            return null;
        }
    }

    private static boolean valid(ProgramDefinition definition, Request request, GateDefinition gate,
                                 GateEvidence evidence, List<String> blockers) {
        if (evidence == null) return false;
        if (evidence.batch() != definition.batch()) blockers.add(gate.id() + " batch mismatch");
        if (!evidence.programId().equals(request.programId())) blockers.add(gate.id() + " program mismatch");
        if (!evidence.sourceVersion().equals(request.sourceVersion())) blockers.add(gate.id() + " version mismatch");
        if (!evidence.organizationId().equals(request.organizationId())) blockers.add(gate.id() + " tenant mismatch");
        if (!evidence.gate().equals(gate.id())) blockers.add(gate.id() + " gate mismatch");
        if (evidence.observedAt().isAfter(request.observedAt())) blockers.add(gate.id() + " future-dated evidence");
        if (evidence.evidenceRefs().isEmpty()) blockers.add(gate.id() + " immutable evidence references missing");
        if (evidence.status() != EvidenceStatus.PASSED) blockers.add(gate.id() + " status is " + evidence.status());
        if (evidence.coverage() < 1.0) blockers.add(gate.id() + " coverage is incomplete");
        if (!evidence.tenantBoundaryPassed()) blockers.add(gate.id() + " tenant boundary failed");
        if (!evidence.legalAndPolicyPassed()) blockers.add(gate.id() + " legal or policy gate failed");
        if (!evidence.humanAccountabilityPassed()) blockers.add(gate.id() + " human accountability failed");
        if (evidence.criticalOpenRisks() > 0) blockers.add(gate.id() + " has critical open risks");
        if (evidence.externalOperationExecuted()) blockers.add(gate.id() + " attempted an external operation");
        return evidence.batch() == definition.batch() && evidence.programId().equals(request.programId())
                && evidence.sourceVersion().equals(request.sourceVersion())
                && evidence.organizationId().equals(request.organizationId())
                && evidence.gate().equals(gate.id()) && !evidence.observedAt().isAfter(request.observedAt())
                && passes(evidence);
    }

    private static boolean passes(GateEvidence evidence) {
        return evidence != null && evidence.status() == EvidenceStatus.PASSED && evidence.coverage() == 1.0
                && evidence.tenantBoundaryPassed() && evidence.legalAndPolicyPassed()
                && evidence.humanAccountabilityPassed() && evidence.criticalOpenRisks() == 0
                && !evidence.evidenceRefs().isEmpty() && !evidence.externalOperationExecuted();
    }

    private static List<String> restrictions(ProgramDefinition definition) {
        return List.of(
                "External legal, financial, human, regulatory, operational and production authorities remain authoritative",
                "Repository tests, generated artifacts and simulations do not establish " + definition.finalGate(),
                "Every company-series control-plane artifact records external_operation_executed=false");
    }
}
