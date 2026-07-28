package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.*;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class ModelEndpointProvisioningTest {

    @Test void everyCatalogModelStaysNotConfiguredWithTodaysDefaultCollaborators() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new UnimplementedModelHealthProbe());
        for (String modelId : ModelCatalog.MODEL_IDS) {
            var result = provisioning.provision("org-a", "catalog:" + modelId, ModelProviderType.ELMOS_MANAGED,
                    "unassigned", modelId, Set.of("CODING_AGENT"));
            assertFalse(result.approved(), modelId + " must not be approved without a real credential");
            assertEquals(List.of("CREDENTIAL_NOT_CONFIGURED"), result.reasonCodes());
        }
    }

    @Test void cliEvidenceReportsAllFourteenModelsAsNotConfigured() {
        String json = ModelEndpointProvisioningCli.run(new EnvModelCredentialSource(), new UnimplementedModelHealthProbe());
        assertEquals(ModelCatalog.MODEL_IDS.size(), countOccurrences(json, "\"approved\": false"));
        assertEquals(0, countOccurrences(json, "\"approved\": true"));
        assertTrue(json.contains("CREDENTIAL_NOT_CONFIGURED"));
    }

    @Test void presentButUnhealthyCredentialStillFailsClosed() {
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        ModelHealthProbe unhealthyProbe = (modelId, credential) ->
                new ModelHealthProbe.Result(false, "VENDOR_REJECTED_KEY", null);
        var provisioning = new ModelEndpointProvisioning(fakeCredential, unhealthyProbe);
        var result = provisioning.provision("org-a", "catalog:claude-opus-5", ModelProviderType.ELMOS_MANAGED,
                "us", "claude-opus-5", Set.of("CODING_AGENT"));
        assertFalse(result.approved());
        assertEquals(List.of("HEALTH_PROBE_UNHEALTHY:VENDOR_REJECTED_KEY"), result.reasonCodes());
    }

    @Test void probeExceptionFailsClosedInsteadOfPropagating() {
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        ModelHealthProbe throwingProbe = (modelId, credential) -> { throw new RuntimeException("network reset"); };
        var provisioning = new ModelEndpointProvisioning(fakeCredential, throwingProbe);
        var result = provisioning.provision("org-a", "catalog:grok-4.5", ModelProviderType.ELMOS_MANAGED,
                "us", "grok-4.5", Set.of("CODING_AGENT"));
        assertFalse(result.approved());
        assertEquals(List.of("HEALTH_PROBE_THREW"), result.reasonCodes());
    }

    @Test void endToEndWithFakeHealthyCredentialProducesAnEndpointThatRouteModelActuallySelects() {
        // Proves the full pipeline (provisioning -> registry -> PrivateExecutionGovernance.routeModel)
        // works end to end. The credential and probe here are test fakes, not real vendor access —
        // that is the honest way to test wiring without claiming any real model is available.
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        ModelHealthProbe healthyProbe = (modelId, credential) ->
                new ModelHealthProbe.Result(true, "OK", "evidence://fake-probe/" + modelId);
        var provisioning = new ModelEndpointProvisioning(fakeCredential, healthyProbe);

        var result = provisioning.provision("org-a", "catalog:claude-opus-5", ModelProviderType.ELMOS_MANAGED,
                "us", "claude-opus-5", Set.of("LONG_TAIL_CODE_FIX"));
        assertTrue(result.approved());
        ModelEndpoint endpoint = result.endpoint().orElseThrow();
        assertTrue(endpoint.approved());
        assertTrue(endpoint.healthy());

        var registry = new ModelEndpointRegistry();
        registry.register(endpoint);
        assertEquals(1, registry.activeEndpoints("org-a").size());

        var governance = new PrivateExecutionGovernance();
        ModelPolicy policy = new ModelPolicy("p1", Set.of(ModelProviderType.ELMOS_MANAGED), Set.of("us"),
                Set.of(DataClassification.OPEN_SOURCE), false, 5000, false, false);
        ModelRequest request = new ModelRequest("inv-1", "org-a", "LONG_TAIL_CODE_FIX", DataClassification.OPEN_SOURCE,
                100, true, BigDecimal.TEN, "a".repeat(64), "b".repeat(64));
        ModelRoutingDecision decision = governance.routeModel(policy, request, registry.activeEndpoints("org-a"), BigDecimal.TEN);

        assertEquals(ModelDecisionStatus.ALLOW, decision.status());
        assertEquals("catalog:claude-opus-5", decision.providerId());
        assertEquals("claude-opus-5", decision.modelVersion());
    }

    @Test void registryRejectsAnUnapprovedEndpoint() {
        var registry = new ModelEndpointRegistry();
        ModelEndpoint unapproved = new ModelEndpoint("catalog:grok-4.5", ModelProviderType.ELMOS_MANAGED, "org-a",
                "us", "grok-4.5", false, false, Set.of("CODING_AGENT"));
        assertThrows(IllegalArgumentException.class, () -> registry.register(unapproved));
    }

    private static int countOccurrences(String haystack, String needle) {
        int count = 0;
        int index = 0;
        while ((index = haystack.indexOf(needle, index)) != -1) {
            count++;
            index += needle.length();
        }
        return count;
    }
}
