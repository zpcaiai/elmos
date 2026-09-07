package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelEndpoint;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Process-memory registry of provisioned {@link ModelEndpoint}s, tenant
 * scoped. This is explicitly not a persistence layer: nothing here survives
 * a restart, there is no database, and no other process can see what one
 * process registered. Only endpoints that came out of
 * {@link ModelEndpointProvisioning#provision} with {@code approved=true} may
 * be registered — this class refuses anything else so it cannot become a
 * side channel for injecting an unapproved endpoint into
 * {@link PrivateExecutionGovernance#routeModel}.
 */
public final class ModelEndpointRegistry {
    private final Map<String, List<ModelEndpoint>> byOrganization = new ConcurrentHashMap<>();

    public void register(ModelEndpoint endpoint) {
        java.util.Objects.requireNonNull(endpoint, "endpoint");
        if (!endpoint.approved() || !endpoint.healthy()) {
            throw new IllegalArgumentException("only an approved and healthy endpoint may be registered: " + endpoint.providerId());
        }
        byOrganization.compute(endpoint.organizationId(), (organizationId, existing) -> {
            List<ModelEndpoint> updated = existing == null ? new java.util.ArrayList<>() : new java.util.ArrayList<>(existing);
            updated.removeIf(candidate -> candidate.providerId().equals(endpoint.providerId())
                    && candidate.modelVersion().equals(endpoint.modelVersion()));
            updated.add(endpoint);
            return List.copyOf(updated);
        });
    }

    public List<ModelEndpoint> activeEndpoints(String organizationId) {
        EnterpriseModels.require(organizationId, "organizationId");
        return byOrganization.getOrDefault(organizationId, List.of());
    }
}
