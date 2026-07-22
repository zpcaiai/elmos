package io.elmos.testquality;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class TestQualityEngineTest {
    private final TestQualityEngineService engine = new TestQualityEngineService();

    @Test void capabilitiesDeclareFailClosedSeparationOfDuties() {
        var capabilities = engine.capabilities();
        assertEquals("ELMOS_TEST_QUALITY", capabilities.engineName());
        assertEquals(false, capabilities.sandboxRequirements().get("workerCanModifyGate"));
        assertEquals(false, capabilities.sandboxRequirements().get("aiAutoPromotion"));
        assertEquals("NOT_CONFIGURED", capabilities.sandboxRequirements().get("runnerStatus"));
    }

    @Test void discoveryFailsClosedWithoutFabricatedEvidence() {
        var response = engine.discover(request("discover"));
        assertEquals(EngineApi.JobStatus.FAILED, response.status());
        assertEquals(EngineApi.ErrorCode.TEST_QUALITY_RUNNER_REQUIRED, response.error().errorCode());
        assertTrue(response.evidenceRefs().isEmpty());
        assertEquals(false, response.result().get("customerCodeExecuted"));
        assertEquals(false, response.result().get("notRunTreatedAsPass"));
    }

    @Test void executionRequiresBothLeasesThenStillRequiresRunner() {
        var missing = execute(Map.of());
        assertEquals(EngineApi.ErrorCode.TEST_ENVIRONMENT_UNAVAILABLE, missing.error().errorCode());
        var leased = execute(Map.of("environmentLeaseApproved", true, "testDataLeaseApproved", true));
        assertEquals(EngineApi.ErrorCode.TEST_QUALITY_RUNNER_REQUIRED, leased.error().errorCode());
    }

    @Test void aiCandidateCannotAutoPromote() {
        var decision = engine.promote(new QualityModels.PromotionRequest("candidate-1", null,
                true, true, true, true, true, true));
        assertFalse(decision.promoted());
        assertTrue(decision.reasonCodes().contains("HUMAN_REVIEW_REQUIRED"));
    }

    @Test void idempotencyIsTenantScopedAndRejectsChangedInput() {
        var first = engine.plan(request("same"));
        assertEquals(first, engine.plan(request("same")));
        var conflict = engine.plan(new EngineApi.JobRequest("org-1", "snapshot-2", "workspace-1", "STANDARD", "corr", "same"));
        assertEquals(EngineApi.ErrorCode.POLICY_BLOCKED, conflict.error().errorCode());
    }

    private EngineApi.JobRequest request(String key) {
        return new EngineApi.JobRequest("org-1", "snapshot-1", "workspace-1", "STANDARD", "corr", key);
    }
    private EngineApi.JobResponse execute(Map<String, Object> policy) {
        return engine.execute(new EngineApi.ExecuteStepRequest("org-1", "run-1", 1,
                new EngineApi.StepDefinition("test-1", EngineApi.ExecutorType.UNIT_TEST, Map.of()),
                "workspace-1", "sha", new EngineApi.ExecutionBudget(60, 60, 1024, 0),
                policy, "corr", "exec-" + policy.size()));
    }
}
