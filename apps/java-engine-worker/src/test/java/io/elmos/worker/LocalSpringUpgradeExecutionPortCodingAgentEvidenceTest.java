package io.elmos.worker;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Exercises {@link LocalSpringUpgradeExecutionPort#codingAgentEvidencePayload} in
 * isolation. That class's constructor requires a real, exact-version JAVA_HOME and
 * Maven executable on disk (see {@code requireJavaHome}/{@code requireMaven}), so it
 * cannot be instantiated in an ordinary unit test; every other behavior of
 * {@code LocalSpringUpgradeExecutionPort#execute} stays covered only by the manual
 * local-environment runs recorded as this pipeline's {@code PASSED_LOCAL} evidence
 * (see ADR-0059). This test covers only the new, pure decision logic added for the
 * Stage.DETERMINISTIC_REPAIR second-failure evidence attachment, so that logic does
 * not ship with zero automated coverage.
 */
class LocalSpringUpgradeExecutionPortCodingAgentEvidenceTest {

    @Test void disabledPortProducesNoEvidencePayload() {
        SpringUpgradeCodingAgentPort disabled =
                new DisabledSpringUpgradeCodingAgentPort("disabled for this test");

        Optional<Map<String, Object>> payload =
                LocalSpringUpgradeExecutionPort.codingAgentEvidencePayload(disabled, "org-a", "run-1");

        assertTrue(payload.isEmpty(),
                "the default (disabled) port must produce no evidence, matching today's exact "
                        + "pre-existing failure behavior with zero change");
    }

    @Test void configuredPortThatThrowsProducesAProvisioningFailedPayload() {
        SpringUpgradeCodingAgentPort throwing = new SpringUpgradeCodingAgentPort() {
            @Override public List<CandidateModel> provisionCandidates(String organizationId, String runId) {
                throw new IllegalStateException("simulated provisioning outage");
            }
            @Override public boolean configured() { return true; }
            @Override public String configurationReason() { return "configured but throws for this test"; }
        };

        Optional<Map<String, Object>> payload =
                LocalSpringUpgradeExecutionPort.codingAgentEvidencePayload(throwing, "org-a", "run-1");

        assertTrue(payload.isPresent());
        assertEquals("PROVISIONING_FAILED", payload.get().get("status"));
        assertEquals("IllegalStateException", payload.get().get("error"));
    }

    @SuppressWarnings("unchecked")
    @Test void configuredPortWithCandidatesProducesACandidatesProvisionedPayload() {
        SpringUpgradeCodingAgentPort.CandidateModel approved =
                new SpringUpgradeCodingAgentPort.CandidateModel("deepseek-v4-pro", true, List.of("OK"));
        SpringUpgradeCodingAgentPort.CandidateModel unapproved =
                new SpringUpgradeCodingAgentPort.CandidateModel(
                        "gpt-5.6-sol", false, List.of("CREDENTIAL_NOT_CONFIGURED"));
        SpringUpgradeCodingAgentPort fake = new SpringUpgradeCodingAgentPort() {
            @Override public List<CandidateModel> provisionCandidates(String organizationId, String runId) {
                assertEquals("org-a", organizationId);
                assertEquals("run-1", runId);
                return List.of(approved, unapproved);
            }
            @Override public boolean configured() { return true; }
            @Override public String configurationReason() { return "configured with fake candidates for this test"; }
        };

        Optional<Map<String, Object>> payload =
                LocalSpringUpgradeExecutionPort.codingAgentEvidencePayload(fake, "org-a", "run-1");

        assertTrue(payload.isPresent());
        assertEquals("CANDIDATES_PROVISIONED", payload.get().get("status"));
        var candidates = (List<Map<String, Object>>) payload.get().get("candidates");
        assertEquals(2, candidates.size());
        var deepseek = candidates.stream()
                .filter(entry -> entry.get("model_id").equals("deepseek-v4-pro")).findFirst().orElseThrow();
        assertEquals(true, deepseek.get("approved"));
        assertEquals(List.of("OK"), deepseek.get("reason_codes"));
        var gpt = candidates.stream()
                .filter(entry -> entry.get("model_id").equals("gpt-5.6-sol")).findFirst().orElseThrow();
        assertEquals(false, gpt.get("approved"));
        assertEquals(List.of("CREDENTIAL_NOT_CONFIGURED"), gpt.get("reason_codes"));
    }
}
