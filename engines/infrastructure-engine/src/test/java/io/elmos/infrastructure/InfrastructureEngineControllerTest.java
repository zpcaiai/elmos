package io.elmos.infrastructure;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InfrastructureEngineControllerTest {
    private final InfrastructureEngineController controller =
            new InfrastructureEngineController(new InfrastructureEngineService());

    @Test void exposesInfrastructureCapabilities() {
        assertEquals("ELMOS_INFRASTRUCTURE", controller.capabilities().engineName());
    }

    @Test void controllerScanRemainsFailClosed() {
        var response = controller.scan(new EngineApi.JobRequest(
                "org-1", "snapshot:1", "workspace:1", "READ_ONLY", "corr", "controller-scan"));
        assertEquals(EngineApi.ErrorCode.INFRASTRUCTURE_RUNNER_REQUIRED, response.error().errorCode());
    }
}
