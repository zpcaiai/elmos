package io.elmos.worker;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class EngineControllerTest {
    @Test void capabilitiesAdvertiseFailClosedExecutionBoundary() {
        var capabilities = new EngineController().capabilities();
        assertEquals("NOT_CONFIGURED_FAIL_CLOSED", capabilities.sandboxRequirements().get("recipeExecution"));
    }

    @Test void unavailableGenericExecutorIsIdempotentAndFailsClosedWithoutFabricatedEvidence() {
        var controller=new EngineController();
        var request=new EngineApi.JobRequest("org","artifact:snapshot","workspace:isolated","scan","corr","same-key");
        var first=controller.scan(request);
        var second=controller.scan(new EngineApi.JobRequest("org","artifact:snapshot","workspace:isolated","scan","corr-retry","same-key"));
        assertEquals(first.jobId(),second.jobId());
        assertEquals(EngineApi.JobStatus.FAILED,first.status());
        assertEquals(EngineApi.ErrorCode.POLICY_BLOCKED,first.error().errorCode());
        assertTrue(first.evidenceRefs().isEmpty());
        assertEquals(Boolean.FALSE,first.result().get("executed"));
        assertEquals(Boolean.FALSE,first.result().get("customerCodeExecuted"));
        assertFalse(first.result().containsKey("simulated"));
        assertThrows(EngineApi.JobConflictException.class,()->controller.cancel(first.jobId(),"org"));
        assertThrows(EngineApi.JobNotFoundException.class,()->controller.job(first.jobId(),"other-org"));
    }

    @Test void sameIdempotencyKeyWithDifferentInputIsRejected() {
        var controller=new EngineController();
        controller.scan(new EngineApi.JobRequest("org","artifact:snapshot-a","workspace:isolated","scan","corr","same-key"));
        assertThrows(EngineApi.IdempotencyConflictException.class,()->controller.scan(
                new EngineApi.JobRequest("org","artifact:snapshot-b","workspace:isolated","scan","corr","same-key")));
    }

    @Test void executeStepReportsMissingApprovedRunnerInsteadOfSuccess() {
        var controller=new EngineController();
        var request=new EngineApi.ExecuteStepRequest("org","run-1",1,
                new EngineApi.StepDefinition("step-1",EngineApi.ExecutorType.OPENREWRITE,Map.of()),
                "workspace:lease","abcdef1",new EngineApi.ExecutionBudget(60,60,1024,0),Map.of(),"corr","execute-key");
        var response=controller.execute(request);
        assertEquals(EngineApi.JobStatus.FAILED,response.status());
        assertEquals(EngineApi.ErrorCode.WORKSPACE_UNAVAILABLE,response.error().errorCode());
        assertEquals("APPROVED_WORKSPACE_RUNNER_NOT_CONFIGURED",response.result().get("reasonCode"));
    }
}
