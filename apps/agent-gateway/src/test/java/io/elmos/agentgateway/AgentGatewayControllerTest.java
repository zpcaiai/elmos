package io.elmos.agentgateway;

import io.elmos.repair.RepairModels.ProviderType;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AgentGatewayControllerTest {
    private final AgentGatewayController controller = new AgentGatewayController();

    @Test void providerPlansRemainPolicyOnlyAndFailClosedForExecution() {
        var plan = controller.providerPlan(ProviderType.CODEX, "/tasks/repair.json");
        assertFalse(plan.networkEnabled());
        assertFalse(plan.dockerSocketMounted());
        assertEquals(Boolean.FALSE, controller.executionCapability().get("configured"));
        assertThrows(IllegalArgumentException.class, () -> controller.providerPlan(ProviderType.HUMAN, "/tasks/repair.json"));
    }
}
