package io.elmos.lowering;

import io.elmos.enterprise.ModelCredentialSource;
import io.elmos.enterprise.ModelHealthProbe;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class LoweringCodingAgentPortTest {

    private static LoweringModels.AgentPacket samplePacket() {
        return new LoweringModels.AgentPacket("task-1", "decl-1", "python", "faithful-first",
                List.of("op-1"), List.of("type-1"), List.of("effect-1"), List.of("obligation-1"),
                List.of("no-network-io"), List.of("pytest"), "a lowered method body", "escalated by planner");
    }

    @Test void disabledPortAlwaysThrows() {
        var port = new DisabledLoweringCodingAgentPort("not configured for this test");
        assertFalse(port.configured());
        assertThrows(IllegalStateException.class, () -> port.provisionCandidates("org-a", samplePacket()));
    }

    @Test void everyCandidateStaysUnapprovedWithNoRealCredential() {
        ModelCredentialSource noCredential = modelId -> Optional.empty();
        var port = new EnterpriseGovernanceLoweringCodingAgentPort(
                List.of("gpt-5.6-sol", "glm-5.2", "deepseek-v4-pro"), noCredential, Map.of(), "global");

        var candidates = port.provisionCandidates("org-a", samplePacket());

        assertEquals(3, candidates.size());
        for (var candidate : candidates) {
            assertFalse(candidate.approved());
            assertEquals(List.of("CREDENTIAL_NOT_CONFIGURED"), candidate.reasonCodes());
        }
    }

    @Test void modelWithAFakeHealthyProbeIsApproved() {
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        ModelHealthProbe healthyProbe = (modelId, credential) ->
                new ModelHealthProbe.Result(true, "OK", "evidence://fake");
        var port = new EnterpriseGovernanceLoweringCodingAgentPort(
                List.of("glm-5.2", "deepseek-v4-pro"), fakeCredential,
                Map.of("deepseek-v4-pro", healthyProbe), "global");

        var candidates = port.provisionCandidates("org-a", samplePacket());

        var glm = candidates.stream().filter(c -> c.modelId().equals("glm-5.2")).findFirst().orElseThrow();
        var deepseek = candidates.stream().filter(c -> c.modelId().equals("deepseek-v4-pro")).findFirst().orElseThrow();
        assertFalse(glm.approved(), "glm-5.2 has no dedicated probe wired in this test");
        assertTrue(deepseek.approved(), "deepseek-v4-pro was given a fake healthy probe");
    }

    @Test void rejectsNullPacket() {
        ModelCredentialSource fakeCredential = modelId -> Optional.of("fake-credential-for-test");
        var port = new EnterpriseGovernanceLoweringCodingAgentPort(
                List.of("deepseek-v4-pro"), fakeCredential, Map.of(), "global");
        assertThrows(IllegalArgumentException.class, () -> port.provisionCandidates("org-a", null));
    }
}
