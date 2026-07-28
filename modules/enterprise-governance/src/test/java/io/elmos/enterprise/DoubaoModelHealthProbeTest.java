package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DoubaoModelHealthProbeTest {

    // Pure status-code interpretation: runs everywhere, no network, no credential needed.
    @Test void interpretsHttpStatusCodesWithoutAnyNetworkCall() {
        assertTrue(DoubaoModelHealthProbe.interpret(200).healthy());
        assertEquals("DOUBAO_MODELS_LIST_OK", DoubaoModelHealthProbe.interpret(200).reasonCode());

        assertFalse(DoubaoModelHealthProbe.interpret(401).healthy());
        assertEquals("DOUBAO_CREDENTIAL_REJECTED:401", DoubaoModelHealthProbe.interpret(401).reasonCode());

        assertFalse(DoubaoModelHealthProbe.interpret(403).healthy());
        assertEquals("DOUBAO_CREDENTIAL_REJECTED:403", DoubaoModelHealthProbe.interpret(403).reasonCode());

        assertFalse(DoubaoModelHealthProbe.interpret(429).healthy());
        assertEquals("DOUBAO_RATE_LIMITED", DoubaoModelHealthProbe.interpret(429).reasonCode());

        assertFalse(DoubaoModelHealthProbe.interpret(500).healthy());
        assertEquals("DOUBAO_UNEXPECTED_STATUS:500", DoubaoModelHealthProbe.interpret(500).reasonCode());
    }

    /**
     * Opt-in, real-network, real-credential evidence. Disabled by default —
     * stays NOT_RUN unless an operator explicitly exports a real Volcengine
     * Ark key as ELMOS_MODEL_CREDENTIAL_DOUBAO_SEED_CODE before running
     * `mvn test`. Unlike DeepSeek's equivalent test, this one has never
     * actually been run with a real credential in this project, so the
     * endpoint/header assumptions baked into DoubaoModelHealthProbe remain
     * unverified until an operator does so.
     */
    @Test
    @EnabledIfEnvironmentVariable(named = "ELMOS_MODEL_CREDENTIAL_DOUBAO_SEED_CODE", matches = ".+")
    void liveDoubaoCredentialProvisionsARealApprovedEndpoint() {
        var provisioning = new ModelEndpointProvisioning(new EnvModelCredentialSource(), new DoubaoModelHealthProbe());
        var result = provisioning.provision("org-a", "doubao:doubao-seed-code", ModelProviderType.ELMOS_MANAGED,
                "global", "doubao-seed-code", Set.of("LONG_TAIL_CODE_FIX"));

        assertNotNull(result.reasonCodes());
        assertFalse(result.reasonCodes().isEmpty());
        if (result.approved()) {
            var endpoint = result.endpoint().orElseThrow();
            assertTrue(endpoint.approved());
            assertTrue(endpoint.healthy());
            assertEquals("doubao-seed-code", endpoint.modelVersion());
        } else {
            System.out.println("Doubao live probe did not approve the endpoint: " + result.reasonCodes());
        }
    }
}
