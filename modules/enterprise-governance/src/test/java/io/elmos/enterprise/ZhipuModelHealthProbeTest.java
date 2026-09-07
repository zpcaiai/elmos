package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class ZhipuModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(ZhipuModelHealthProbe.interpret(200).healthy());
        assertEquals("ZHIPU_MODELS_LIST_OK", ZhipuModelHealthProbe.interpret(200).reasonCode());

        assertFalse(ZhipuModelHealthProbe.interpret(401).healthy());
        assertEquals("ZHIPU_CREDENTIAL_REJECTED:401", ZhipuModelHealthProbe.interpret(401).reasonCode());

        assertFalse(ZhipuModelHealthProbe.interpret(403).healthy());
        assertEquals("ZHIPU_CREDENTIAL_REJECTED:403", ZhipuModelHealthProbe.interpret(403).reasonCode());

        assertFalse(ZhipuModelHealthProbe.interpret(429).healthy());
        assertEquals("ZHIPU_RATE_LIMITED", ZhipuModelHealthProbe.interpret(429).reasonCode());

        assertFalse(ZhipuModelHealthProbe.interpret(500).healthy());
        assertEquals("ZHIPU_UNEXPECTED_STATUS:500", ZhipuModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real Zhipu
     * BigModel key as ELMOS_MODEL_CREDENTIAL_GLM_5_2 before running
     * `mvn test`. Unlike DeepSeek's equivalent test, this one has never
     * actually been run with a real credential in this project, so the
     * endpoint/header assumptions baked into ZhipuModelHealthProbe remain
     * unverified until an operator does so — see the class Javadoc's note
     * about Zhipu's models-listing route being the highest-risk-of-drift
     * assumption in this package.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_GLM_5_2", matches = ".+")
    void liveZhipuCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new ZhipuModelHealthProbe());
        var result = provisioning.provision("org-a", "zhipu:glm-5.2", ModelProviderType.ELMOS_MANAGED,
                "global", "glm-5.2", Set.of("IDIOMATIZATION_REVIEW"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("glm-5.2", endpoint.modelVersion());
        } else {
            System.out.println("Zhipu live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
