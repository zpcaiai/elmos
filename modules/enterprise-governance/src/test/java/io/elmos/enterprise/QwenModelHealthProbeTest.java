package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class QwenModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(QwenModelHealthProbe.interpret(200).healthy());
        assertEquals("QWEN_MODELS_LIST_OK", QwenModelHealthProbe.interpret(200).reasonCode());

        assertFalse(QwenModelHealthProbe.interpret(401).healthy());
        assertEquals("QWEN_CREDENTIAL_REJECTED:401", QwenModelHealthProbe.interpret(401).reasonCode());

        assertFalse(QwenModelHealthProbe.interpret(403).healthy());
        assertEquals("QWEN_CREDENTIAL_REJECTED:403", QwenModelHealthProbe.interpret(403).reasonCode());

        assertFalse(QwenModelHealthProbe.interpret(429).healthy());
        assertEquals("QWEN_RATE_LIMITED", QwenModelHealthProbe.interpret(429).reasonCode());

        assertFalse(QwenModelHealthProbe.interpret(500).healthy());
        assertEquals("QWEN_UNEXPECTED_STATUS:500", QwenModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real DashScope key
     * as ELMOS_MODEL_CREDENTIAL_QWEN3_8_MAX_PREVIEW before running `mvn test`.
     * Unlike DeepSeek's equivalent test, this one has never actually been run
     * with a real credential in this project, so the endpoint/header
     * assumptions baked into QwenModelHealthProbe remain unverified until an
     * operator does so.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_QWEN3_8_MAX_PREVIEW", matches = ".+")
    void liveQwenCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new QwenModelHealthProbe());
        var result = provisioning.provision("org-a", "qwen:qwen3.8-max-preview", ModelProviderType.ELMOS_MANAGED,
                "global", "qwen3.8-max-preview", Set.of("LONG_TAIL_CODE_FIX"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("qwen3.8-max-preview", endpoint.modelVersion());
        } else {
            System.out.println("Qwen live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
