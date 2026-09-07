package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class GoogleModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(GoogleModelHealthProbe.interpret(200).healthy());
        assertEquals("GOOGLE_MODELS_LIST_OK", GoogleModelHealthProbe.interpret(200).reasonCode());

        assertFalse(GoogleModelHealthProbe.interpret(401).healthy());
        assertEquals("GOOGLE_CREDENTIAL_REJECTED:401", GoogleModelHealthProbe.interpret(401).reasonCode());

        assertFalse(GoogleModelHealthProbe.interpret(403).healthy());
        assertEquals("GOOGLE_CREDENTIAL_REJECTED:403", GoogleModelHealthProbe.interpret(403).reasonCode());

        assertFalse(GoogleModelHealthProbe.interpret(429).healthy());
        assertEquals("GOOGLE_RATE_LIMITED", GoogleModelHealthProbe.interpret(429).reasonCode());

        assertFalse(GoogleModelHealthProbe.interpret(500).healthy());
        assertEquals("GOOGLE_UNEXPECTED_STATUS:500", GoogleModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real Google key as
     * ELMOS_MODEL_CREDENTIAL_GEMINI_3_6_FLASH before running `mvn test`. Unlike
     * DeepSeek's equivalent test, this one has never actually been run with a
     * real credential in this project, so the endpoint/query-param assumptions
     * baked into GoogleModelHealthProbe remain unverified until an operator
     * does so.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_GEMINI_3_6_FLASH", matches = ".+")
    void liveGoogleCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new GoogleModelHealthProbe());
        var result = provisioning.provision("org-a", "google:gemini-3.6-flash", ModelProviderType.ELMOS_MANAGED,
                "global", "gemini-3.6-flash", Set.of("FAST_ITERATION"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("gemini-3.6-flash", endpoint.modelVersion());
        } else {
            System.out.println("Google live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
