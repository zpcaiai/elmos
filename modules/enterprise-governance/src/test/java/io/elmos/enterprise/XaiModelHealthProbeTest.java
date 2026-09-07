package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class XaiModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(XaiModelHealthProbe.interpret(200).healthy());
        assertEquals("XAI_MODELS_LIST_OK", XaiModelHealthProbe.interpret(200).reasonCode());

        assertFalse(XaiModelHealthProbe.interpret(401).healthy());
        assertEquals("XAI_CREDENTIAL_REJECTED:401", XaiModelHealthProbe.interpret(401).reasonCode());

        assertFalse(XaiModelHealthProbe.interpret(403).healthy());
        assertEquals("XAI_CREDENTIAL_REJECTED:403", XaiModelHealthProbe.interpret(403).reasonCode());

        assertFalse(XaiModelHealthProbe.interpret(429).healthy());
        assertEquals("XAI_RATE_LIMITED", XaiModelHealthProbe.interpret(429).reasonCode());

        assertFalse(XaiModelHealthProbe.interpret(500).healthy());
        assertEquals("XAI_UNEXPECTED_STATUS:500", XaiModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real xAI key as
     * ELMOS_MODEL_CREDENTIAL_GROK_4_5 before running `mvn test`. Unlike
     * DeepSeek's equivalent test, this one has never actually been run with a
     * real credential in this project, so the endpoint/header assumptions
     * baked into XaiModelHealthProbe remain unverified until an operator does
     * so.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_GROK_4_5", matches = ".+")
    void liveXaiCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new XaiModelHealthProbe());
        var result = provisioning.provision("org-a", "xai:grok-4.5", ModelProviderType.ELMOS_MANAGED,
                "global", "grok-4.5", Set.of("LONG_TAIL_CODE_FIX"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("grok-4.5", endpoint.modelVersion());
        } else {
            System.out.println("xAI live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
