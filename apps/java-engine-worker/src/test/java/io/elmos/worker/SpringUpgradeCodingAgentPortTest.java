package io.elmos.worker;

import io.elmos.enterprise.ModelCredentialSource;
import io.elmos.enterprise.ModelHealthProbe;
import io.elmos.enterprise.UnimplementedModelHealthProbe;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class SpringUpgradeCodingAgentPortTest {

    @Test void disabledPortAlwaysThrowsBlockedException() {
        var port = new DisabledSpringUpgradeCodingAgentPort("not configured for this test");
        assertFalse(port.configured());
        var error = assertThrows(SpringUpgradeModels.BlockedException.class,
                () -> port.provisionCandidates("org-a", "run-1"));
        assertEquals("CODING_AGENT_NOT_CONFIGURED", error.code());
    }

    @Test void everyCandidateStaysUnapprovedWithNoRealCredentialOrProbe() {
        ModelCredentialSource noCredential = modelId -> Optional.empty();
        var port = new EnterpriseGovernanceSpringUpgradeCodingAgentPort(
                List.of("gpt-5.6-sol", "claude-opus-5", "deepseek-v4-pro"),
                noCredential, Map.of(), "global");

        List<SpringUpgradeCodingAgentPort.CandidateModel> candidates = port.provisionCandidates("org-a", "run-1");

        assertEquals(3, candidates.size());
        for (var candidate : candidates) {
            assertFalse(candidate.approved(), candidate.modelId() + " must not be approved without a credential");
            assertEquals(List.of("CREDENTIAL_NOT_CONFIGURED"), candidate.reasonCodes());
        }
    }

    @Test void modelWithoutADedicatedProbeFailsClosedEvenWithACredential() {
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        var port = new EnterpriseGovernanceSpringUpgradeCodingAgentPort(
                List.of("claude-opus-5"), fakeCredential, Map.of(), "global");

        var candidates = port.provisionCandidates("org-a", "run-1");

        assertEquals(1, candidates.size());
        assertFalse(candidates.get(0).approved());
        assertEquals(List.of("HEALTH_PROBE_UNHEALTHY:HEALTH_PROBE_NOT_IMPLEMENTED"), candidates.get(0).reasonCodes());
    }

    @Test void modelWithAFakeHealthyProbeIsApproved() {
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        ModelHealthProbe healthyProbe = (modelId, credential) ->
                new ModelHealthProbe.Result(true, "OK", "evidence://fake");
        var port = new EnterpriseGovernanceSpringUpgradeCodingAgentPort(
                List.of("gpt-5.6-sol", "deepseek-v4-pro"), fakeCredential,
                Map.of("deepseek-v4-pro", healthyProbe), "global");

        var candidates = port.provisionCandidates("org-a", "run-1");

        assertEquals(2, candidates.size());
        var gpt = candidates.stream().filter(c -> c.modelId().equals("gpt-5.6-sol")).findFirst().orElseThrow();
        var deepseek = candidates.stream().filter(c -> c.modelId().equals("deepseek-v4-pro")).findFirst().orElseThrow();
        assertFalse(gpt.approved(), "gpt-5.6-sol has no dedicated probe wired in this test and must stay unapproved");
        assertTrue(deepseek.approved(), "deepseek-v4-pro was given a fake healthy probe and should be approved");
    }

    @Test void constructorRejectsEmptyCandidateList() {
        assertThrows(IllegalArgumentException.class, () ->
                new EnterpriseGovernanceSpringUpgradeCodingAgentPort(List.of(), modelId -> Optional.empty(), Map.of(), "global"));
    }
}
