package io.elmos.developerworkflow;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class SemanticConflictResolver {
    public record Conflict(String base, String priorGenerated, String current, String regenerated,
                           Ownership ownership, boolean ownerApproved) {}
    public record Resolution(Decision decision, String code, String content) {}

    public Resolution resolve(Conflict conflict) {
        if (conflict.ownership()==Ownership.HUMAN && !conflict.ownerApproved()) return new Resolution(Decision.ESCALATE,"HUMAN_OWNER_DECISION_REQUIRED",conflict.current());
        if (conflict.current().equals(conflict.priorGenerated())) return new Resolution(Decision.ALLOW,"SAFE_REGENERATION",conflict.regenerated());
        if (conflict.regenerated().equals(conflict.priorGenerated())) return new Resolution(Decision.ALLOW,"PRESERVE_HUMAN_EDIT",conflict.current());
        if (conflict.current().equals(conflict.regenerated())) return new Resolution(Decision.ALLOW,"CHANGES_ALREADY_CONVERGED",conflict.current());
        return new Resolution(Decision.ESCALATE,"AMBIGUOUS_SEMANTIC_CONFLICT",conflict.current());
    }
}
