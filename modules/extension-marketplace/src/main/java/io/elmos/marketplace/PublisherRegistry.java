package io.elmos.marketplace;

import static io.elmos.marketplace.MarketplaceModels.*;

public final class PublisherRegistry {
    public PolicyDecision validate(PublisherProfile publisher) {
        if (!publisher.verified() || !publisher.active()) return PolicyDecision.deny("PUBLISHER_NOT_VERIFIED_ACTIVE");
        if (!publisher.mfa() || !publisher.separationOfDuties()) return PolicyDecision.deny("PUBLISHER_SECURITY_CONTROLS_REQUIRED");
        if (publisher.identityEvidence().isEmpty() || publisher.activeSigningKeys().isEmpty()) return PolicyDecision.deny("PUBLISHER_IDENTITY_OR_KEY_MISSING");
        if (publisher.securityContact()==null || !publisher.securityContact().contains("@")) return PolicyDecision.deny("SECURITY_CONTACT_REQUIRED");
        return PolicyDecision.allow("PUBLISHER_VERIFIED",publisher.publisherId());
    }
}
