package io.elmos.infrastructure;

import java.util.Map;

/** External capability port. Core policy never embeds provider SDKs or host execution. */
public interface InfrastructureProvider {
    record ProviderRequest(String organizationId, String credentialLeaseRef, String region,
                           String immutablePlanRef, Map<String, Object> configuration) {}
    record ProviderResult(String providerRequestId, String status, Map<String, Object> facts,
                          String rawEvidenceRef) {}

    ProviderResult discover(ProviderRequest request);
    ProviderResult applyApprovedPlan(ProviderRequest request);
    ProviderResult validate(ProviderRequest request);
}
