package io.elmos.mainframe;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MainframeEngineServiceTest {
    private final MainframeEngineService service = new MainframeEngineService();

    @Test void capabilitiesAreFailClosedAndMultiPath() {
        var c = service.capabilities();
        assertEquals("ELMOS_MAINFRAME", c.engineName());
        assertTrue(c.supportedTargetVersions().contains("KEEP_ON_Z"));
        assertTrue(c.supportedTargetVersions().contains("TRANSFORM_LANGUAGE"));
        assertEquals(false, c.sandboxRequirements().get("controlPlaneExecution"));
        assertEquals("DENY", c.sandboxRequirements().get("productionWritesDefault"));
    }

    @Test void discoveryDoesNotFabricateEvidenceWithoutAdapter() {
        var result = service.discover(job("discover-1"));
        assertEquals(EngineApi.JobStatus.FAILED, result.status());
        assertEquals(EngineApi.ErrorCode.MAINFRAME_RUNNER_REQUIRED, result.error().errorCode());
        assertTrue(result.evidenceRefs().isEmpty());
        assertEquals(false, result.result().get("customerCodeExecuted"));
    }

    @Test void executeRequiresLeaseAndDatasetScope() {
        var result = service.execute(execute(Map.of()));
        assertEquals(EngineApi.ErrorCode.MAINFRAME_LEASE_REQUIRED, result.error().errorCode());
        assertEquals("NOT_RUN", result.result().get("externalStatus"));
    }

    @Test void productionWriteRequiresIndependentApproval() {
        var result = service.execute(execute(Map.of("mainframeJobLeaseApproved", true,
                "datasetScopeApproved", true, "productionWriteRequested", true)));
        assertEquals(EngineApi.ErrorCode.MAINFRAME_PRODUCTION_APPROVAL_REQUIRED, result.error().errorCode());
        assertEquals(false, result.result().get("productionStateChanged"));
    }

    @Test void arbitraryJclIsAlwaysBlocked() {
        var result = service.execute(execute(Map.of("mainframeJobLeaseApproved", true,
                "datasetScopeApproved", true, "arbitraryJcl", true)));
        assertEquals(EngineApi.ErrorCode.POLICY_BLOCKED, result.error().errorCode());
    }

    @Test void businessRuleNeedsOwnerApprovalAndTraceability() {
        var candidate = service.approveRule(new MainframeModels.RuleApprovalRequest("rule-1", "",
                MainframeModels.RuleEvidence.SOURCE_INFERRED, true, true, true));
        assertFalse(candidate.authoritative());
        var approved = service.approveRule(new MainframeModels.RuleApprovalRequest("rule-1", "owner-1",
                MainframeModels.RuleEvidence.BUSINESS_APPROVED, true, true, true));
        assertTrue(approved.authoritative());
    }

    @Test void jobsAreTenantScoped() {
        var response = service.discover(job("tenant-job"));
        assertThrows(IllegalArgumentException.class, () -> service.job("other-org", response.jobId()));
    }

    private static EngineApi.JobRequest job(String key) {
        return new EngineApi.JobRequest("org-1", "snapshot://sha", "workspace://1", "STANDARD", "corr-1", key);
    }
    private static EngineApi.ExecuteStepRequest execute(Map<String,Object> policy) {
        return new EngineApi.ExecuteStepRequest("org-1", "run-1", 1,
                new EngineApi.StepDefinition("step-1", EngineApi.ExecutorType.MAINFRAME_BUILD, Map.of()),
                "workspace://1", "sha", new EngineApi.ExecutionBudget(60, 60, 1024, 0),
                policy, "corr-1", "exec-" + policy.hashCode());
    }
}
