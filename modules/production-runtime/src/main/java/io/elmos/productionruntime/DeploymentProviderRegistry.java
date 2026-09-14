package io.elmos.productionruntime;

import java.util.Map;
import java.util.Set;

/** Operator-installed providers; no class names, commands or endpoints from request JSON. */
public record DeploymentProviderRegistry(Map<String, DeploymentToolExecutor.Provider> providers) {
    public DeploymentProviderRegistry {
        providers = Map.copyOf(providers);
        if (!providers.keySet().containsAll(Set.of("iac.apply", "iac.destroy", "helm.render",
                "gitops.proposal", "gitops.reconcile"))) {
            throw new IllegalArgumentException("DEPLOYMENT_REQUIRED_PROVIDERS_MISSING");
        }
    }
}
