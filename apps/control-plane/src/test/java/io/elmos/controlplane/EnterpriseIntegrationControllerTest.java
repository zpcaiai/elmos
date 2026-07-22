package io.elmos.controlplane;

import io.elmos.application.IntegrationCutoverGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class EnterpriseIntegrationControllerTest {
    private final EnterpriseIntegrationController controller = new EnterpriseIntegrationController();

    @Test void controlPlaneIsJudgeNotIntegrationExecutor() {
        var c = controller.capabilities();
        assertEquals("ELMOS_ENTERPRISE_INTEGRATION", c.engine());
        assertFalse(c.executesIntegrationChanges());
        assertTrue(c.prohibitedDirectActions().contains("RESET_PRODUCTION_OFFSET"));
        assertTrue(c.prohibitedDirectActions().contains("AUTO_CUTOVER"));
    }

    @Test void decommissionBlocksWhileLegacyPartnerTrafficRemains() {
        var result = controller.evaluateDecommission(new IntegrationCutoverGovernance.Evidence("sha", "sha", true,
                true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, true, true,
                true, true, true, false, true, true, true, true,
                List.of("evidence://integration")));
        assertEquals(IntegrationCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("LEGACY_PARTNER_TRAFFIC_REMAINS"));
    }
}
