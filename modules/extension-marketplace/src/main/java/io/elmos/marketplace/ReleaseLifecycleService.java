package io.elmos.marketplace;

import java.util.Map;
import java.util.Set;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class ReleaseLifecycleService {
    private static final Map<ReleaseStatus,Set<ReleaseStatus>> TRANSITIONS=Map.of(
            ReleaseStatus.DRAFT,Set.of(ReleaseStatus.SUBMITTED,ReleaseStatus.WITHDRAWN),
            ReleaseStatus.SUBMITTED,Set.of(ReleaseStatus.CERTIFIED,ReleaseStatus.WITHDRAWN),
            ReleaseStatus.CERTIFIED,Set.of(ReleaseStatus.PUBLISHED,ReleaseStatus.REVOKED),
            ReleaseStatus.PUBLISHED,Set.of(ReleaseStatus.QUARANTINED,ReleaseStatus.REVOKED,ReleaseStatus.WITHDRAWN),
            ReleaseStatus.QUARANTINED,Set.of(ReleaseStatus.PUBLISHED,ReleaseStatus.REVOKED),
            ReleaseStatus.REVOKED,Set.of(),ReleaseStatus.WITHDRAWN,Set.of());

    public PolicyDecision transition(ReleaseRecord release,ReleaseStatus target,boolean independentApproval) {
        if (!Digests.exact(release.digest()) || !release.immutable()) return PolicyDecision.deny("IMMUTABLE_DIGEST_BOUND_RELEASE_REQUIRED");
        if (!TRANSITIONS.getOrDefault(release.status(),Set.of()).contains(target)) return PolicyDecision.deny("INVALID_RELEASE_TRANSITION");
        if ((target==ReleaseStatus.CERTIFIED || target==ReleaseStatus.PUBLISHED) && !independentApproval) return PolicyDecision.deny("INDEPENDENT_RELEASE_APPROVAL_REQUIRED");
        return PolicyDecision.allow("RELEASE_TRANSITION_AUTHORIZED",release.status()+"->"+target);
    }
    public PolicyDecision executable(ReleaseRecord release) {
        if (release.status()==ReleaseStatus.REVOKED || release.status()==ReleaseStatus.QUARANTINED || release.status()==ReleaseStatus.WITHDRAWN) return PolicyDecision.deny("RELEASE_EXECUTION_BLOCKED");
        if (release.status()!=ReleaseStatus.PUBLISHED) return PolicyDecision.deny("RELEASE_NOT_PUBLISHED");
        return PolicyDecision.allow("RELEASE_EXECUTABLE",release.digest());
    }
}
