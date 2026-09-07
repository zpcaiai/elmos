package io.elmos.controlplane;

import io.elmos.application.SecurityAuthorizationGovernance;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SecurityComplianceControllerTest {
    private final SecurityComplianceController controller = new SecurityComplianceController();

    @Test void controlPlaneDoesNotExecuteToolsOrGrantFormalCertification() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_SECURITY_COMPLIANCE", capabilities.engine());
        assertTrue(capabilities.status().contains("NOT_CONFIGURED"));
        assertTrue(capabilities.prohibitedActions().contains("RUN_HOST_SCANNER"));
        assertTrue(capabilities.prohibitedActions().contains("ACCEPT_RISK"));
        assertTrue(capabilities.prohibitedActions().contains("GRANT_FORMAL_CERTIFICATION"));
    }

    @Test void openCriticalRiskIsDenied() {
        var result = controller.evaluate(new SecurityAuthorizationGovernance.Evidence("org-1", "boundary-1", "abc123",
                "sha256:artifact", "deploy-1", "sha256:evidence", true, true, true, true,
                true, false, false, true, false, "security-owner", Instant.now().plusSeconds(3600), Map.of(),
                List.of("evidence://assessment")));
        assertEquals(SecurityAuthorizationGovernance.Decision.DENIED, result.decision());
        assertFalse(result.releaseEligible()); assertFalse(result.externalCertificationGranted());
    }
}
