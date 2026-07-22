package io.elmos.infrastructure;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static io.elmos.engine.api.EngineApi.*;
import static org.junit.jupiter.api.Assertions.*;

class InfrastructureEngineTest {
    private final InfrastructureEngineService engine = new InfrastructureEngineService();

    @Test void capabilitiesDeclareFourTracksAndSixFailClosedRunners() {
        var capabilities = engine.capabilities();
        assertEquals("ELMOS_INFRASTRUCTURE", capabilities.engineName());
        assertEquals(4, capabilities.solutionFormats().size());
        assertEquals(6, capabilities.runnerProfiles().size());
        assertEquals("NOT_CONFIGURED", capabilities.sandboxRequirements().get("runnerStatus"));
    }

    @Test void discoveryFailsClosedWithoutRunnerAndFabricatesNothing() {
        var response = engine.scan(request("scan-1"));
        assertEquals(JobStatus.FAILED, response.status());
        assertEquals(ErrorCode.INFRASTRUCTURE_RUNNER_REQUIRED, response.error().errorCode());
        assertTrue(response.evidenceRefs().isEmpty());
        assertEquals(false, response.result().get("providerOperationExecuted"));
        assertEquals(false, response.result().get("customerInfrastructureChanged"));
        assertEquals("NOT_RUN", response.result().get("externalStatus"));
    }

    @Test void mutatingStepRequiresImmutablePlanBeforeApprovalOrRunner() {
        var step = new StepDefinition("apply-network", ExecutorType.IAC_APPLIER, Map.of());
        var request = new ExecuteStepRequest("org-1", "run-1", 1, step, "workspace:1", "abc",
                new ExecutionBudget(60, 60, 1024, 0), Map.of(), "corr", "execute-1");
        assertEquals(ErrorCode.INFRASTRUCTURE_PLAN_REQUIRED, engine.executeStep(request).error().errorCode());
    }

    @Test void planWithoutApprovalStillFailsBeforeRunner() {
        var step = new StepDefinition("apply-network", ExecutorType.IAC_APPLIER, Map.of());
        var request = new ExecuteStepRequest("org-1", "run-1", 1, step, "workspace:1", "abc",
                new ExecutionBudget(60, 60, 1024, 0), Map.of("immutablePlanRef", "sha256:plan"), "corr", "execute-2");
        assertEquals(ErrorCode.INFRASTRUCTURE_APPROVAL_REQUIRED, engine.executeStep(request).error().errorCode());
    }

    @Test void idempotencyIsTenantScopedAndRejectsInputReuse() {
        var first = engine.scan(request("same-key"));
        var repeated = engine.scan(request("same-key"));
        assertEquals(first.jobId(), repeated.jobId());
        var changed = new EngineApi.JobRequest("org-1", "snapshot:other", "workspace:1", "READ_ONLY", "corr", "same-key");
        assertEquals(ErrorCode.POLICY_BLOCKED, engine.scan(changed).error().errorCode());
    }

    private EngineApi.JobRequest request(String key) {
        return new EngineApi.JobRequest("org-1", "snapshot:1", "workspace:1", "READ_ONLY", "corr", key);
    }
}
