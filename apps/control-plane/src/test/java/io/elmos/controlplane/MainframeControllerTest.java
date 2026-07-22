package io.elmos.controlplane;

import io.elmos.application.MainframeCutoverGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MainframeControllerTest {
    private final MainframeController controller = new MainframeController();

    @Test void capabilitiesSeparateControlPlaneAndZosExecution() {
        var c = controller.capabilities();
        assertEquals("ELMOS_MAINFRAME", c.engine());
        assertTrue(c.prohibitedActions().contains("EXECUTE_ZOS_ON_CONTROL_PLANE"));
        assertTrue(c.prohibitedActions().contains("AUTO_SWITCH_DATA_AUTHORITY"));
    }

    @Test void unknownExternalConsumerBlocksDecommission() {
        var result = controller.evaluateDecommission(new MainframeCutoverGovernance.Evidence("sha", "sha", true, true,
                true, true, true, true, true, true, true, true, true, false, true, true,
                List.of("evidence://mainframe")));
        assertEquals(MainframeCutoverGovernance.Decision.FAIL, result.decision());
        assertFalse(result.decommissionAuthorized());
        assertFalse(result.workerModifiedRoute());
    }
}
