package io.elmos.developerworkflow;

import java.util.List;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class OwnershipPolicyEngine {
    private final List<ProtectedRegion> regions;

    public OwnershipPolicyEngine(List<ProtectedRegion> regions) {
        this.regions = List.copyOf(regions);
    }

    public PolicyDecision authorize(EditRequest edit) {
        for (ProtectedRegion region : regions) {
            if (!region.path().equals(edit.path()) || edit.endLine() < region.startLine() || edit.startLine() > region.endLine()) continue;
            if (region.ownership() == Ownership.HUMAN && !region.owner().equals(edit.actor())) {
                return PolicyDecision.deny("HUMAN_REGION_PROTECTED");
            }
            if (region.approvalRequired() && !edit.approved()) return PolicyDecision.escalate("OWNER_APPROVAL_REQUIRED", region.owner());
        }
        return PolicyDecision.allow("EDIT_WITHIN_OWNERSHIP_POLICY", edit.path());
    }
}
