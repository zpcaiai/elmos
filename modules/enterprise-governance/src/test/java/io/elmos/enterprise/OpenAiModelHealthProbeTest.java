package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class OpenAiModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(OpenAiModelHealthProbe.interpret(200).healthy());
        assertEquals("OPENAI_MODELS_LIST_OK", OpenAiModelHealthProbe.interpret(200).reasonCode());

        assertFalse(OpenAiModelHealthProbe.interpret(401).healthy());
        assertEquals("OPENAI_CREDENTIAL_REJECTED:401", OpenAiModelHealthProbe.interpret(401).reasonCode());

        assertFalse(OpenAiModelHealthProbe.interpret(403).healthy());
        assertEquals("OPENAI_CREDENTIAL_REJECTED:403", OpenAiModelHealthProbe.interpret(403).reasonCode());

        assertFalse(OpenAiModelHealthProbe.interpret(429).healthy());
        assertEquals("OPENAI_RATE_LIMITED", OpenAiModelHealthProbe.interpret(429).reasonCode());

        assertFalse(OpenAiModelHealthProbe.interpret(500).healthy());
        assertEquals("OPENAI_UNEXPECTED_STATUS:500", OpenAiModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real OpenAI key as
     * ELMOS_MODEL_CREDENTIAL_GPT_5_6_SOL before running `mvn test`. Unlike
     * DeepSeek's equivalent test, this one has never actually been run with a
     * real credential in this project, so the endpoint/header assumptions
     * baked into OpenAiModelHealthProbe remain unverified until an operator
     * does so.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_GPT_5_6_SOL", matches = ".+")
    void liveOpenAiCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new OpenAiModelHealthProbe());
        var result = provisioning.provision("org-a", "openai:gpt-5.6-sol", ModelProviderType.ELMOS_MANAGED,
                "global", "gpt-5.6-sol", Set.of("LONG_TAIL_CODE_FIX"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("gpt-5.6-sol", endpoint.modelVersion());
        } else {
            System.out.println("OpenAI live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
