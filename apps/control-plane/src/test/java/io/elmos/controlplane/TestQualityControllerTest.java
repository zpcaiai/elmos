package io.elmos.controlplane;

import io.elmos.application.TestQualityGateGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class TestQualityControllerTest {
    private final TestQualityController controller = new TestQualityController();

    @Test void capabilitiesKeepExecutionAndGateAuthoritySeparated() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_TEST_QUALITY", capabilities.engine());
        assertTrue(capabilities.prohibitedActions().contains("RUN_TESTS_ON_CONTROL_PLANE"));
        assertTrue(capabilities.prohibitedActions().contains("MODIFY_QUALITY_GATE"));
        assertTrue(capabilities.prohibitedActions().contains("AUTO_PROMOTE_AI_TEST"));
    }

    @Test void criticalUncoveredRiskFailsIndependentDecision() {
        var result = controller.evaluate(new TestQualityGateGovernance.Evidence("sha", "sha", true,
                10, 10, 10, 10, 0, 1, 0, 0, 0, true, true,
                List.of("evidence://quality"), Map.of()));
        assertEquals(TestQualityGateGovernance.Decision.FAIL, result.decision());
        assertFalse(result.releaseAuthorized());
        assertFalse(result.gateModifiedByWorker());
    }
}
