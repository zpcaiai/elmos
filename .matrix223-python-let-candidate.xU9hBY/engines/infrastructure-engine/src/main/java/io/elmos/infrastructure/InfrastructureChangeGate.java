package io.elmos.infrastructure;

import java.util.ArrayList;
import java.util.List;

import static io.elmos.infrastructure.InfrastructureModels.ChangeKind;
import static io.elmos.infrastructure.InfrastructureModels.ChangePlan;

public final class InfrastructureChangeGate {
    public record Decision(boolean allowed, boolean automatic, List<String> blockers) {}

    public Decision evaluate(ChangePlan plan) {
        var blockers = new ArrayList<String>();
        if (plan.evidenceRefs().isEmpty()) blockers.add("INFRASTRUCTURE_EVIDENCE_MISSING");
        if (!plan.policyPassed()) blockers.add("INFRASTRUCTURE_POLICY_FAILED");
        if (!plan.securityPassed()) blockers.add("INFRASTRUCTURE_SECURITY_FAILED");
        if (!plan.costPassed()) blockers.add("INFRASTRUCTURE_COST_FAILED");
        if (plan.rollbackRef() == null || plan.rollbackRef().isBlank()) blockers.add("ROLLBACK_REFERENCE_MISSING");
        boolean write = plan.changeKind() != ChangeKind.DISCOVERY && plan.changeKind() != ChangeKind.PLAN;
        if (write && (plan.approvedBy() == null || plan.approvedBy().isBlank())) {
            blockers.add("NAMED_INFRASTRUCTURE_APPROVAL_REQUIRED");
        }
        return new Decision(blockers.isEmpty(), !write, List.copyOf(blockers));
    }
}
