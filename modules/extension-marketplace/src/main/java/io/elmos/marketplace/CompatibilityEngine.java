package io.elmos.marketplace;

import static io.elmos.marketplace.MarketplaceModels.*;

public final class CompatibilityEngine {
    public PolicyDecision evaluate(CompatibilityContract contract,String runtimeProductVersion,long nowEpochSecond) {
        if (!contract.publicApi()) return PolicyDecision.deny("PRIVATE_API_NOT_A_COMPATIBILITY_PROMISE");
        if (!contract.supportedProductVersions().contains(runtimeProductVersion)) return PolicyDecision.deny("PRODUCT_VERSION_UNSUPPORTED");
        if (!runtimeProductVersion.equals(contract.productVersion())) return PolicyDecision.escalate("EXACT_TUPLE_CONFORMANCE_REQUIRED",runtimeProductVersion);
        if (contract.protocolVersion().isBlank() || contract.sdkVersion().isBlank()) return PolicyDecision.deny("PROTOCOL_AND_SDK_VERSION_REQUIRED");
        if (contract.deprecationExitEpochSecond()>0 && contract.deprecationExitEpochSecond()<=nowEpochSecond) return PolicyDecision.deny("DEPRECATION_EXIT_REACHED");
        return PolicyDecision.allow("COMPATIBILITY_TUPLE_VALID",runtimeProductVersion+"/"+contract.protocolVersion()+"/"+contract.sdkVersion());
    }
}
