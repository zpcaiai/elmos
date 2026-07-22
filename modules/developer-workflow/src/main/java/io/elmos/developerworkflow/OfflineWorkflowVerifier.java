package io.elmos.developerworkflow;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class OfflineWorkflowVerifier {
    public PolicyDecision verify(OfflineBundle bundle) {
        if (bundle.networkEnabled()) return PolicyDecision.deny("OFFLINE_NETWORK_MUST_BE_DISABLED");
        if (!bundle.signed() || !bundle.trustedRoots().contains(bundle.trustRoot())) return PolicyDecision.deny("OFFLINE_BUNDLE_UNTRUSTED");
        if (!bundle.bundleDigest().equals(bundle.expectedDigest()) || !Digests.exactSha256(bundle.bundleDigest())) return PolicyDecision.deny("OFFLINE_BUNDLE_DIGEST_MISMATCH");
        if (!bundle.grantedPermissions().containsAll(bundle.requestedPermissions())) return PolicyDecision.deny("OFFLINE_PERMISSION_NOT_PREGRANTED");
        return PolicyDecision.allow("OFFLINE_BUNDLE_VERIFIED",bundle.bundleDigest());
    }
}
