package io.elmos.application;

import java.time.Instant;
import java.util.*;

/** Independent control-plane adjudication. It can prepare a decision but can never grant it. */
public final class CrossDomainDecisionGovernance {
    public enum Domain { SOFTWARE_DELIVERY_PLATFORM, AI_PLATFORM, EDGE_IOT_INDUSTRIAL, OPERATIONS_SRE_ITSM, ENTERPRISE_ARCHITECTURE }
    public enum Status { BLOCKED, READY_FOR_HUMAN_DECISION }
    public record Evidence(String evidenceRef, String gate, String sourceAuthority, Instant observedAt,
                           Instant expiresAt, boolean independent, boolean passed) {}
    public record Request(String organizationId, Domain domain, String decisionType, List<Evidence> evidence,
                          List<String> approvalRefs, boolean productionStateChangeRequested) {}
    public record Result(Status status, Domain domain, List<String> missingGates, List<String> rejectedEvidenceRefs,
                         boolean eligibleForExecution, boolean humanDecisionGranted,
                         boolean productionStateChanged, String explanation) {}

    private static final Map<Domain, Set<String>> REQUIRED_GATES = Map.of(
            Domain.SOFTWARE_DELIVERY_PLATFORM, Set.of("SCM", "PIPELINE", "ARTIFACT", "PLATFORM_ACCEPTANCE"),
            Domain.AI_PLATFORM, Set.of("DATA", "REPRODUCIBILITY", "EVALUATION", "SAFETY", "RESPONSIBLE_AI", "COST"),
            Domain.EDGE_IOT_INDUSTRIAL, Set.of("READ_PATH", "WRITE_PATH", "SAFETY", "SIL", "HIL", "ROLLBACK"),
            Domain.OPERATIONS_SRE_ITSM, Set.of("SERVICE_TOPOLOGY", "SLO", "BUSINESS_IMPACT", "VERIFICATION", "ROLLBACK"),
            Domain.ENTERPRISE_ARCHITECTURE, Set.of("SOURCE_AUTHORITY", "OPTION", "TRADEOFF", "DEPENDENCY", "CONFORMANCE"));

    public Result evaluate(Request request, Instant now) {
        Objects.requireNonNull(request, "request"); Objects.requireNonNull(now, "now");
        require(request.organizationId(), "organizationId");
        Objects.requireNonNull(request.domain(), "domain"); require(request.decisionType(), "decisionType");
        var evidence = request.evidence() == null ? List.<Evidence>of() : List.copyOf(request.evidence());
        var approvals = request.approvalRefs() == null ? List.<String>of() : List.copyOf(request.approvalRefs());
        var rejected = evidence.stream().filter(item -> item == null || blank(item.evidenceRef()) || blank(item.gate())
                        || blank(item.sourceAuthority()) || item.observedAt() == null || item.expiresAt() == null
                        || item.observedAt().isAfter(now) || !item.expiresAt().isAfter(now) || !item.independent() || !item.passed())
                .map(item -> item == null || blank(item.evidenceRef()) ? "UNREFERENCED_EVIDENCE" : item.evidenceRef()).sorted().toList();
        var validGates = evidence.stream().filter(Objects::nonNull).filter(item -> !rejected.contains(item.evidenceRef()))
                .map(Evidence::gate).collect(java.util.stream.Collectors.toUnmodifiableSet());
        var missing = REQUIRED_GATES.get(request.domain()).stream().filter(gate -> !validGates.contains(gate)).sorted().toList();
        boolean approvalMissing = request.productionStateChangeRequested() && approvals.stream().noneMatch(ref -> !blank(ref));
        if (!rejected.isEmpty() || !missing.isEmpty() || approvalMissing) {
            var required = new ArrayList<>(missing);
            if (approvalMissing) required.add("INDEPENDENT_HUMAN_APPROVAL");
            return new Result(Status.BLOCKED, request.domain(), List.copyOf(required), rejected,
                    false, false, false, "current independent evidence and explicit human authority are required");
        }
        return new Result(Status.READY_FOR_HUMAN_DECISION, request.domain(), List.of(), List.of(),
                false, false, false, "all machine-checkable gates passed; an authorized human must decide and the worker must execute separately");
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
    private static void require(String value, String name) { if (blank(value)) throw new IllegalArgumentException(name + " is required"); }
}
