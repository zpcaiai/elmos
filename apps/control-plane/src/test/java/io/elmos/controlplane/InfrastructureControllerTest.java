package io.elmos.controlplane;

import io.elmos.application.InfrastructureCutoverGovernance;
import org.junit.jupiter.api.Test;

import java.util.List;

import static io.elmos.application.InfrastructureCutoverGovernance.Decision.*;
import static io.elmos.application.InfrastructureCutoverGovernance.Stage.*;
import static org.junit.jupiter.api.Assertions.*;

class InfrastructureControllerTest {
    private final InfrastructureController controller = new InfrastructureController();

    @Test void keepsProviderMutationOutOfControlPlane() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_INFRASTRUCTURE", capabilities.engine());
        assertEquals(4, capabilities.tracks().size());
        assertTrue(capabilities.prohibitedActions().contains("APPLY_PRODUCTION"));
        assertTrue(capabilities.prohibitedActions().contains("DELETE_RESOURCE"));
        assertTrue(capabilities.status().contains("NOT_CONFIGURED"));
    }

    @Test void trafficCutoverRequiresAllIndependentGatesAndNamedApproval() {
        assertEquals(HUMAN_REVIEW, controller.evaluateCutover(evidence(CANARY_RUNNING, TRAFFIC_CUTOVER, true, null)).decision());
        assertEquals(ADVANCE, controller.evaluateCutover(evidence(CANARY_RUNNING, TRAFFIC_CUTOVER, true, "platform-owner")).decision());
        var held = controller.evaluateCutover(evidence(CANARY_RUNNING, TRAFFIC_CUTOVER, false, "platform-owner"));
        assertEquals(HOLD, held.decision());
        assertTrue(held.blockers().contains("NETWORK_ENFORCEMENT_FAILED"));
    }

    @Test void stageSkippingIsBlocked() {
        assertEquals(BLOCKED, controller.evaluateCutover(evidence(DISCOVERY, TRAFFIC_CUTOVER, true, "owner")).decision());
    }

    private InfrastructureCutoverGovernance.Evidence evidence(
            InfrastructureCutoverGovernance.Stage current,
            InfrastructureCutoverGovernance.Stage requested,
            boolean network,
            String approval) {
        return new InfrastructureCutoverGovernance.Evidence("org-1", current, requested,
                true, true, true, true, network, true, true, true, true, true,
                true, true, true, true, true, List.of("evidence://infrastructure-cutover"), approval);
    }
}
