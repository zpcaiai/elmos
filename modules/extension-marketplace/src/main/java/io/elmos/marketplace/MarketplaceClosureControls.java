package io.elmos.marketplace;

import java.math.BigDecimal;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class MarketplaceClosureControls {
    public PolicyDecision reconcileRuntime(RuntimeHealth health) {
        if (!Digests.exact(health.expectedDigest()) || !health.expectedDigest().equals(health.observedDigest())) return PolicyDecision.deny("RUNTIME_DIGEST_DRIFT");
        if (health.openCriticalIncidents()!=0 || health.leakedCredentials()!=0 || health.orphanProcesses()!=0) return PolicyDecision.deny("RUNTIME_RECONCILIATION_INCOMPLETE");
        if (health.quarantined()) return PolicyDecision.deny("RUNTIME_QUARANTINED");
        return PolicyDecision.allow("RUNTIME_RECONCILED",health.expectedDigest());
    }
    public PolicyDecision verifyOfflineMirror(OfflineMirror mirror) {
        if (mirror.networkEnabled()) return PolicyDecision.deny("OFFLINE_NETWORK_DENIED");
        if (!mirror.signed() || !Digests.exact(mirror.bundleDigest()) || !mirror.bundleDigest().equals(mirror.expectedDigest()) || !mirror.trustedRoots().contains(mirror.trustRoot())) return PolicyDecision.deny("OFFLINE_BUNDLE_UNTRUSTED");
        if (!mirror.onlineGrantedPermissions().containsAll(mirror.requestedPermissions())) return PolicyDecision.deny("OFFLINE_RIGHTS_EXPANSION_DENIED");
        if (mirror.revocationAgeSeconds()>mirror.maximumRevocationAgeSeconds()) return PolicyDecision.deny("OFFLINE_REVOCATION_STATE_STALE");
        return PolicyDecision.allow("OFFLINE_MIRROR_VERIFIED",mirror.bundleDigest());
    }
    public PolicyDecision reconcileSettlement(Settlement settlement) {
        if (settlement.openFraudFinding()) return PolicyDecision.deny("OPEN_FRAUD_FINDING");
        BigDecimal distributed=settlement.refunds().add(settlement.taxes()).add(settlement.publisherShare()).add(settlement.platformShare()).add(settlement.hold());
        if (settlement.gross().compareTo(distributed)!=0 || settlement.gross().compareTo(settlement.providerBilled())!=0) return PolicyDecision.deny("SETTLEMENT_CONSERVATION_BROKEN");
        return PolicyDecision.allow("SETTLEMENT_RECONCILED",settlement.gross().toPlainString());
    }
    public PolicyDecision validateEol(EolPlan plan) {
        if (!plan.notifiedTenants().containsAll(plan.installedTenants())) return PolicyDecision.deny("CUSTOMER_NOTIFICATION_INCOMPLETE");
        if (!plan.exportedTenants().containsAll(plan.installedTenants()) || !plan.uninstalledTenants().containsAll(plan.installedTenants())) return PolicyDecision.deny("DATA_PORTABILITY_OR_UNINSTALL_INCOMPLETE");
        if (!plan.residualDependencies().isEmpty()) return PolicyDecision.deny("RESIDUAL_EOL_DEPENDENCIES");
        if (!plan.replacementAvailable() && !plan.installedTenants().isEmpty()) return PolicyDecision.escalate("EOL_REPLACEMENT_DECISION_REQUIRED","customers:"+plan.installedTenants().size());
        return PolicyDecision.allow("EOL_CLOSURE_READY","customers:"+plan.installedTenants().size());
    }
}
