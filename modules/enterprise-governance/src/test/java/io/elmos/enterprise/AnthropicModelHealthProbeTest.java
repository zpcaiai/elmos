package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class AnthropicModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(AnthropicModelHealthProbe.interpret(200).healthy());
        assertEquals("ANTHROPIC_MODELS_LIST_OK", AnthropicModelHealthProbe.interpret(200).reasonCode());

        assertFalse(AnthropicModelHealthProbe.interpret(401).healthy());
        assertEquals("ANTHROPIC_CREDENTIAL_REJECTED:401", AnthropicModelHealthProbe.interpret(401).reasonCode());

        assertFalse(AnthropicModelHealthProbe.interpret(403).healthy());
        assertEquals("ANTHROPIC_CREDENTIAL_REJECTED:403", AnthropicModelHealthProbe.interpret(403).reasonCode());

        assertFalse(AnthropicModelHealthProbe.interpret(429).healthy());
        assertEquals("ANTHROPIC_RATE_LIMITED", AnthropicModelHealthProbe.interpret(429).reasonCode());

        assertFalse(AnthropicModelHealthProbe.interpret(500).healthy());
        assertEquals("ANTHROPIC_UNEXPECTED_STATUS:500", AnthropicModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real Anthropic key
     * as ELMOS_MODEL_CREDENTIAL_CLAUDE_OPUS_5 before running `mvn test`. Unlike
     * DeepSeek's equivalent test, this one has never actually been run with a
     * real credential in this project, so the endpoint/header assumptions
     * baked into AnthropicModelHealthProbe remain unverified until an operator
     * does so.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_CLAUDE_OPUS_5", matches = ".+")
    void liveAnthropicCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new AnthropicModelHealthProbe());
        var result = provisioning.provision("org-a", "anthropic:claude-opus-5", ModelProviderType.ELMOS_MANAGED,
                "global", "claude-opus-5", Set.of("LONG_TAIL_CODE_FIX"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("claude-opus-5", endpoint.modelVersion());
        } else {
            System.out.println("Anthropic live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
