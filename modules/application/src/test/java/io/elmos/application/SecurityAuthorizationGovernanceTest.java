package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SecurityAuthorizationGovernanceTest {
    private final SecurityAuthorizationGovernance governance = new SecurityAuthorizationGovernance();

    @Test void ordinarySystemCanReceiveOnlyInternalTimeBoundDecision() {
        var result = governance.evaluate(evidence(false, false, false, true, "security-owner", Map.of()), Instant.parse("2026-07-21T00:00:00Z"));
        assertEquals(SecurityAuthorizationGovernance.Decision.AUTHORIZED, result.decision());
        assertTrue(result.internalDecisionOnly()); assertFalse(result.externalCertificationGranted()); assertTrue(result.releaseEligible());
    }

    @Test void criticalRiskAndIncidentFailClosed() {
        assertEquals(SecurityAuthorizationGovernance.Decision.DENIED,
                governance.evaluate(evidence(true, false, false, true, "owner", Map.of()), Instant.parse("2026-07-21T00:00:00Z")).decision());
        assertEquals(SecurityAuthorizationGovernance.Decision.SUSPENDED,
                governance.evaluate(evidence(false, true, false, true, "owner", Map.of()), Instant.parse("2026-07-21T00:00:00Z")).decision());
    }

    @Test void criticalSystemCannotBeAutomaticallyAuthorized() {
        var result = governance.evaluate(evidence(false, false, true, false, null, Map.of()), Instant.parse("2026-07-21T00:00:00Z"));
        assertEquals(SecurityAuthorizationGovernance.Decision.REASSESSMENT_REQUIRED, result.decision());
        assertTrue(result.blockers().contains("CRITICAL_SYSTEM_INDEPENDENT_HUMAN_APPROVAL_REQUIRED"));
    }

    private static SecurityAuthorizationGovernance.Evidence evidence(boolean criticalRisk, boolean incident,
                                                                      boolean criticalSystem, boolean independent,
                                                                      String approver, Map<String, String> conditions) {
        return new SecurityAuthorizationGovernance.Evidence("org-1", "boundary-1", "abc123", "sha256:artifact",
                "deploy-1", "sha256:evidence", true, true, true, true, criticalRisk, false, incident,
                independent, criticalSystem, approver, Instant.parse("2026-08-21T00:00:00Z"), conditions,
                List.of("evidence://control-assessment"));
    }
}
