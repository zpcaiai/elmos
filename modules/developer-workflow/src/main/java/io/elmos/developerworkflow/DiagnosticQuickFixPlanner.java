package io.elmos.developerworkflow;

import java.util.List;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class DiagnosticQuickFixPlanner {
    public record Diagnostic(String id, String artifactDigest, String path, int startLine, int endLine) {}
    public record FixCandidate(String diagnosticId, String artifactDigest, String path, int startLine,
                               int endLine, String patchDigest, Set<String> postconditionTests) {
        public FixCandidate { postconditionTests=Set.copyOf(postconditionTests); }
    }
    public record Plan(Decision decision, String code, FixCandidate candidate, List<String> requiredActions) {
        public Plan { requiredActions=List.copyOf(requiredActions); }
    }

    public Plan plan(Diagnostic diagnostic, FixCandidate candidate, OwnershipPolicyEngine ownership, String actor) {
        if (!diagnostic.id().equals(candidate.diagnosticId()) || !diagnostic.artifactDigest().equals(candidate.artifactDigest())) return denied("STALE_DIAGNOSTIC_BINDING");
        if (!diagnostic.path().equals(candidate.path()) || candidate.startLine()<diagnostic.startLine() || candidate.endLine()>diagnostic.endLine()) return denied("FIX_OUTSIDE_DIAGNOSTIC_RANGE");
        if (!Digests.exactSha256(candidate.patchDigest()) || candidate.postconditionTests().isEmpty()) return denied("FIX_EVIDENCE_INCOMPLETE");
        PolicyDecision decision=ownership.authorize(new EditRequest(candidate.path(),candidate.startLine(),candidate.endLine(),actor,false));
        if (decision.decision()!=Decision.ALLOW) return new Plan(decision.decision(),decision.code(),candidate,List.of("obtain-owner-approval"));
        return new Plan(Decision.ALLOW,"FIX_CANDIDATE_READY",candidate,List.of("preview","run-postconditions","request-approval"));
    }
    private static Plan denied(String code) { return new Plan(Decision.DENY,code,null,List.of()); }
}
