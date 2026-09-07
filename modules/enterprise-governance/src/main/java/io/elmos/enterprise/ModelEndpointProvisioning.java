package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelEndpoint;
import io.elmos.enterprise.EnterpriseModels.ModelProviderType;

import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * The "→ 产生已批准的 ModelEndpoint" step referenced from
 * {@code docs/adr/ADR-0059-coding-agent-model-catalog.md}: turns a catalog
 * model id into a real {@link ModelEndpoint} that {@link PrivateExecutionGovernance#routeModel}
 * can actually select — or, today, into a documented reason it did not.
 *
 * This class performs no network I/O itself. It orchestrates a
 * {@link ModelCredentialSource} and a {@link ModelHealthProbe}, both
 * pluggable, and is fail-closed at every step: a missing credential, a
 * failed probe, or an unexpected exception from either collaborator all
 * produce an unapproved result with a reason code, never a guessed
 * {@code approved=true}.
 */
public final class ModelEndpointProvisioning {

    public record ProvisioningResult(String modelId, Optional<ModelEndpoint> endpoint, List<String> reasonCodes) {
        public ProvisioningResult {
            EnterpriseModels.require(modelId, "modelId");
            reasonCodes = List.copyOf(reasonCodes);
            if (endpoint == null) throw new IllegalArgumentException("endpoint optional must not be null");
        }

        public boolean approved() {
            return endpoint.isPresent();
        }
    }

    private final ModelCredentialSource credentialSource;
    private final ModelHealthProbe healthProbe;

    public ModelEndpointProvisioning(ModelCredentialSource credentialSource, ModelHealthProbe healthProbe) {
        this.credentialSource = java.util.Objects.requireNonNull(credentialSource, "credentialSource");
        this.healthProbe = java.util.Objects.requireNonNull(healthProbe, "healthProbe");
    }

    public ProvisioningResult provision(String organizationId, String providerId, ModelProviderType type,
                                        String region, String modelId, Set<String> profiles) {
        EnterpriseModels.require(organizationId, "organizationId");
        EnterpriseModels.require(providerId, "providerId");
        EnterpriseModels.require(region, "region");
        EnterpriseModels.require(modelId, "modelId");
        if (type == null) throw new IllegalArgumentException("type is required");
        Set<String> copiedProfiles = Set.copyOf(profiles);

        Optional<String> credential;
        try {
            credential = credentialSource.credentialFor(modelId);
        } catch (RuntimeException error) {
            return new ProvisioningResult(modelId, Optional.empty(), List.of("CREDENTIAL_LOOKUP_FAILED"));
        }
        if (credential.isEmpty()) {
            return new ProvisioningResult(modelId, Optional.empty(), List.of("CREDENTIAL_NOT_CONFIGURED"));
        }

        ModelHealthProbe.Result probeResult;
        try {
            probeResult = healthProbe.probe(modelId, credential.get());
        } catch (RuntimeException error) {
            return new ProvisioningResult(modelId, Optional.empty(), List.of("HEALTH_PROBE_THREW"));
        }
        if (probeResult == null || !probeResult.healthy()) {
            String reason = probeResult == null ? "HEALTH_PROBE_RETURNED_NULL" : "HEALTH_PROBE_UNHEALTHY:" + probeResult.reasonCode();
            return new ProvisioningResult(modelId, Optional.empty(), List.of(reason));
        }

        ModelEndpoint endpoint = new ModelEndpoint(providerId, type, organizationId, region, modelId,
                true, true, copiedProfiles);
        return new ProvisioningResult(modelId, Optional.of(endpoint), List.of("HEALTH_PROBE_PASSED"));
    }
}
