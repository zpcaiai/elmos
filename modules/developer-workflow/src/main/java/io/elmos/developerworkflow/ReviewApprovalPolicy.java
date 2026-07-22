package io.elmos.developerworkflow;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class ReviewApprovalPolicy {
    public PolicyDecision validate(Approval approval, String exactCommit, String exactArtifact, long nowEpochSecond) {
        if (approval.author().equals(approval.reviewer()) || !approval.independent()) return PolicyDecision.deny("SEPARATION_OF_DUTIES_REQUIRED");
        if (!approval.commitDigest().equals(exactCommit) || !approval.artifactDigest().equals(exactArtifact)) return PolicyDecision.deny("APPROVAL_SCOPE_MISMATCH");
        if (approval.expiresAtEpochSecond()<=nowEpochSecond) return PolicyDecision.deny("APPROVAL_EXPIRED");
        return PolicyDecision.allow("APPROVAL_VALID",approval.commitDigest());
    }
}
