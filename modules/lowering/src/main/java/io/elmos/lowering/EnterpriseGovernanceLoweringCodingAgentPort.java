package io.elmos.lowering;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import io.elmos.enterprise.ModelCredentialSource;
import io.elmos.enterprise.ModelEndpointProvisioning;
import io.elmos.enterprise.ModelHealthProbe;
import io.elmos.enterprise.UnimplementedModelHealthProbe;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Real implementation backed by {@code modules/enterprise-governance} (see
 * ADR-0059). Mirrors {@code io.elmos.worker.EnterpriseGovernanceSpringUpgradeCodingAgentPort}
 * one-for-one: same fail-closed provisioning call per candidate model id,
 * same "no dedicated probe means always unhealthy" default. Kept as a
 * near-duplicate rather than a shared abstraction because the two callers
 * (Spring long-tail repair, cross-language lowering) sit in different Maven
 * modules that do not depend on each other, and this class is small enough
 * that a shared abstraction would cost more in indirection than it saves.
 */
public final class EnterpriseGovernanceLoweringCodingAgentPort implements LoweringCodingAgentPort {
    private final List<String> candidateModelIds;
    private final ModelCredentialSource credentialSource;
    private final Map<String, ModelHealthProbe> probesByModelId;
    private final ModelHealthProbe defaultProbe = new UnimplementedModelHealthProbe();
    private final String region;

    public EnterpriseGovernanceLoweringCodingAgentPort(List<String> candidateModelIds,
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
    public List<CandidateModel> provisionCandidates(String organizationId, LoweringModels.AgentPacket packet) {
        requireText(organizationId, "organizationId");
        if (packet == null) throw new IllegalArgumentException("packet is required");
        List<CandidateModel> results = new ArrayList<>();
        for (String modelId : candidateModelIds) {
            ModelHealthProbe probe = probesByModelId.getOrDefault(modelId, defaultProbe);
            var provisioning = new ModelEndpointProvisioning(credentialSource, probe);
            var result = provisioning.provision(organizationId, "lowering-coding-agent:" + modelId,
                    ModelProviderType.ELMOS_MANAGED, region, modelId,
                    Set.of("LONG_TAIL_CODE_FIX", "IDIOMATIZATION_REVIEW"));
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
