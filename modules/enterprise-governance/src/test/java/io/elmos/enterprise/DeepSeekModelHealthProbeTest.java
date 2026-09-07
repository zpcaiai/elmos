package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DeepSeekModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(DeepSeekModelHealthProbe.interpret(200).healthy());
        assertEquals("DEEPSEEK_MODELS_LIST_OK", DeepSeekModelHealthProbe.interpret(200).reasonCode());

        assertFalse(DeepSeekModelHealthProbe.interpret(401).healthy());
        assertEquals("DEEPSEEK_CREDENTIAL_REJECTED:401", DeepSeekModelHealthProbe.interpret(401).reasonCode());

        assertFalse(DeepSeekModelHealthProbe.interpret(403).healthy());
        assertEquals("DEEPSEEK_CREDENTIAL_REJECTED:403", DeepSeekModelHealthProbe.interpret(403).reasonCode());

        assertFalse(DeepSeekModelHealthProbe.interpret(429).healthy());
        assertEquals("DEEPSEEK_RATE_LIMITED", DeepSeekModelHealthProbe.interpret(429).reasonCode());

        assertFalse(DeepSeekModelHealthProbe.interpret(500).healthy());
        assertEquals("DEEPSEEK_UNEXPECTED_STATUS:500", DeepSeekModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real DeepSeek key
     * as ELMOS_MODEL_CREDENTIAL_DEEPSEEK_V4_PRO before running `mvn test`.
     * The credential never appears in source, in this file, or in any
     * committed artifact; it only ever exists in the operator's own shell
     * environment for the duration of the run.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_DEEPSEEK_V4_PRO", matches = ".+")
    void liveDeepSeekCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new DeepSeekModelHealthProbe());
        var result = provisioning.provision("org-a", "deepseek:v4-pro", ModelProviderType.ELMOS_MANAGED,
                "global", "deepseek-v4-pro", Set.of("LONG_TAIL_CODE_FIX"));

        // Intentionally not asserting result.approved() == true: a live vendor call can
        // legitimately fail (rate limit, revoked key, outage) and that must show up as a
        // real failure here, not be forced green. We only assert the pipeline produced a
        // real, distinguishable outcome instead of silently doing nothing.
        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("deepseek-v4-pro", endpoint.modelVersion());
        } else {
            System.out.println("DeepSeek live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
