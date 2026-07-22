package io.elmos.securitycompliance;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SecurityComplianceEngineTest {
    private final SecurityComplianceEngineService engine = new SecurityComplianceEngineService();

    @Test void capabilitiesDeclareHorizontalFailClosedBoundary() {
        var capabilities = engine.capabilities();
        assertEquals("ELMOS_SECURITY_COMPLIANCE", capabilities.engineName());
        assertEquals(7, capabilities.supportedSourceVersions().size());
        assertTrue(capabilities.runnerProfiles().stream().allMatch(value -> value.endsWith("NOT_CONFIGURED")));
        assertEquals("DENY_BY_DEFAULT", capabilities.sandboxRequirements().get("network"));
        assertEquals(false, capabilities.sandboxRequirements().get("formalCertification"));
    }

    @Test void scanFailsClosedAndIsTenantScopedAndIdempotent() {
        var request = request("org-a", "scan-1");
        var first = engine.scan(request); var again = engine.scan(request);
        assertEquals(first, again);
        assertEquals(EngineApi.ErrorCode.SECURITY_TOOL_UNAVAILABLE, first.error().errorCode());
        assertEquals("NOT_RUN", first.result().get("externalStatus"));
        assertEquals(false, first.result().get("evidenceFabricated"));
        assertNotEquals(first, engine.job("org-b", first.jobId()));
    }

    @Test void activeTestNeedsExplicitApprovalBeforeAdapterSelection() {
        var response = engine.executeStep(new EngineApi.ExecuteStepRequest("org-a", "run-1", 1,
                new EngineApi.StepDefinition("dast", EngineApi.ExecutorType.DAST, Map.of("target", "prod")),
                "workspace://a", "abc123", new EngineApi.ExecutionBudget(30, 30, 1_000, 0),
                Map.of("activeTestApproved", false), "corr-1", "execute-1"));
        assertEquals(EngineApi.ErrorCode.SECURITY_TEST_AUTHORIZATION_REQUIRED, response.error().errorCode());
        assertEquals(false, response.result().get("customerTargetChanged"));
    }

    @Test void internalAuthorizationIsTimeBoundAndNeverExternalCertification() {
        var result = engine.authorize(new SecurityModels.AuthorizationRequest("org-a", "boundary-1", "STANDARD",
                "abc123", "sha256:artifact", "deploy-7", "sha256:evidence", List.of("evidence://assessment"),
                true, true, false, false, false, true, "security-owner",
                Instant.now().plusSeconds(3600), Map.of()));
        assertEquals(SecurityModels.AuthorizationDecision.AUTHORIZED, result.decision());
        assertTrue(result.internalDecisionOnly());
        assertFalse(result.externalCertificationGranted());
    }

    @Test void criticalSystemRequiresIndependentHumanApprovalAndRejectsOpenCriticalRisk() {
        var incomplete = engine.authorize(new SecurityModels.AuthorizationRequest("org-a", "boundary-1", "CRITICAL_SYSTEM",
                "abc123", "sha256:artifact", "deploy-7", "sha256:evidence", List.of("evidence://assessment"),
                true, true, false, false, false, false, null,
                Instant.now().plusSeconds(3600), Map.of()));
        assertEquals(SecurityModels.AuthorizationDecision.REASSESSMENT_REQUIRED, incomplete.decision());
        var denied = engine.authorize(new SecurityModels.AuthorizationRequest("org-a", "boundary-1", "CRITICAL_SYSTEM",
                "abc123", "sha256:artifact", "deploy-7", "sha256:evidence", List.of("evidence://assessment"),
                true, true, true, false, false, true, "risk-owner",
                Instant.now().plusSeconds(3600), Map.of()));
        assertEquals(SecurityModels.AuthorizationDecision.DENIED, denied.decision());
    }

    private static EngineApi.JobRequest request(String org, String key) {
        return new EngineApi.JobRequest(org, "snapshot://a", "workspace://a", "STANDARD", "corr-1", key);
    }
}
