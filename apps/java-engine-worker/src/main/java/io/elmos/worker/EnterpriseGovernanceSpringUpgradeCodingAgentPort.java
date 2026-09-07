package io.elmos.worker;

import io.elmos.enterprise.ModelCredentialSource;
import io.elmos.enterprise.ModelEndpointProvisioning;
import io.elmos.enterprise.ModelHealthProbe;
import io.elmos.enterprise.UnimplementedModelHealthProbe;
import io.elmos.enterprise.EnterpriseModels.ModelProviderType;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Real implementation backed by {@code modules/enterprise-governance}'s
 * provisioning pipeline (see ADR-0059). For each configured candidate model
 * id it runs a fresh {@link ModelEndpointProvisioning#provision} attempt
 * using that model's dedicated {@link ModelHealthProbe} if one exists, or
 * {@link UnimplementedModelHealthProbe} (always fails closed) otherwise.
 * Today only {@code deepseek-v4-pro} and {@code deepseek-v4-flash} have a
 * real probe ({@code io.elmos.enterprise.DeepSeekModelHealthProbe}); every
 * other candidate will report {@code HEALTH_PROBE_NOT_IMPLEMENTED} until a
 * real vendor client is written for it.
 */
final class EnterpriseGovernanceSpringUpgradeCodingAgentPort implements SpringUpgradeCodingAgentPort {
    private final List<String> candidateModelIds;
    private final ModelCredentialSource credentialSource;
    private final Map<String, ModelHealthProbe> probesByModelId;
    private final ModelHealthProbe defaultProbe = new UnimplementedModelHealthProbe();
    private final String region;

    EnterpriseGovernanceSpringUpgradeCodingAgentPort(List<String> candidateModelIds,
                                                      ModelCredentialSource credentialSource,
                                                      Map<String, ModelHealthProbe> probesByModelId,
                                                      String region) {
        if (candidateModelIds == null || candidateModelIds.isEmpty()) {
            throw new IllegalArgumentException("candidateModelIds must not be empty");
        }
        this.candidateModelIds = List.copyOf(candidateModelIds);
        this.credentialSource = java.util.Objects.requireNonNull(credentialSource, "credentialSource");
        this.probesByModelId = Map.copyOf(probesByModelId);
        this.region = requireText(region, "region");
    }

    @Override
    public List<CandidateModel> provisionCandidates(String organizationId, String runId) {
        requireText(organizationId, "organizationId");
        requireText(runId, "runId");
        List<CandidateModel> results = new ArrayList<>();
        for (String modelId : candidateModelIds) {
            ModelHealthProbe probe = probesByModelId.getOrDefault(modelId, defaultProbe);
            var provisioning = new ModelEndpointProvisioning(credentialSource, probe);
            var result = provisioning.provision(organizationId, "spring-coding-agent:" + modelId,
                    ModelProviderType.ELMOS_MANAGED, region, modelId, Set.of("LONG_TAIL_CODE_FIX"));
            results.add(new CandidateModel(modelId, result.approved(), result.reasonCodes()));
        }
        return List.copyOf(results);
    }

    @Override public boolean configured() { return true; }
    @Override public String configurationReason() {
        return "Configured with " + candidateModelIds.size() + " candidate model id(s): " + candidateModelIds;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
        return value;
    }
}
