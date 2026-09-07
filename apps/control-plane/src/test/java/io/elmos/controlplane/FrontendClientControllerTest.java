package io.elmos.controlplane;

import io.elmos.application.FrontendClientReleaseGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;

import static io.elmos.application.FrontendClientReleaseGovernance.Decision.*;
import static io.elmos.application.FrontendClientReleaseGovernance.Stage.*;
import static org.junit.jupiter.api.Assertions.*;

class FrontendClientControllerTest {
    private final FrontendClientController controller = new FrontendClientController();

    @Test void keepsExecutionAndExternalPublicationOutOfTheControlPlane() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_FRONTEND_CLIENT", capabilities.engine());
        assertTrue(capabilities.prohibitedActions().contains("EXECUTE_CUSTOMER_CODE"));
        assertTrue(capabilities.prohibitedActions().contains("AUTO_PUBLISH_APP_STORE"));
        assertTrue(capabilities.status().contains("NOT_CONFIGURED"));
    }

    @Test void fullReleaseNeedsNamedHumanApproval() {
        var evidence = new FrontendClientReleaseGovernance.ReleaseEvidence("org-1", PROGRESSIVE, FULL,
                true, true, true, true, true, true, true, true, true, true, List.of("ev"), null);
        assertEquals(HUMAN_REVIEW, controller.evaluateRelease(evidence).decision());
    }
}
