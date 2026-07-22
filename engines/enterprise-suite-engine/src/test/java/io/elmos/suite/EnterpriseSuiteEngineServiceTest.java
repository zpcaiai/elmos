package io.elmos.suite;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class EnterpriseSuiteEngineServiceTest {
    private final EnterpriseSuiteEngineService service = new EnterpriseSuiteEngineService();

    @Test void capabilitiesCoverFourSuiteFamiliesAndFailClosed() {
        var c = service.capabilities();
        assertEquals("ELMOS_ENTERPRISE_SUITE", c.engineName());
        assertTrue(c.languages().contains("SAP_ECC"));
        assertTrue(c.languages().contains("ORACLE_EBS"));
        assertTrue(c.languages().contains("DYNAMICS_365"));
        assertTrue(c.languages().contains("SALESFORCE"));
        assertEquals(false, c.sandboxRequirements().get("controlPlaneExecution"));
        assertEquals("DENY", c.sandboxRequirements().get("productionMutationDefault"));
    }

    @Test void discoveryDoesNotFabricateEvidenceWithoutAdapter() {
        var result = service.scan(job("scan-1"));
        assertEquals(EngineApi.JobStatus.FAILED, result.status());
        assertEquals(EngineApi.ErrorCode.SUITE_RUNNER_REQUIRED, result.error().errorCode());
        assertTrue(result.evidenceRefs().isEmpty());
        assertEquals(false, result.result().get("evidenceFabricated"));
    }

    @Test void executeRequiresLeaseAndEnvironmentScope() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.SAP_VALIDATION, Map.of()));
        assertEquals(EngineApi.ErrorCode.SUITE_LEASE_REQUIRED, result.error().errorCode());
        assertEquals("NOT_RUN", result.result().get("externalStatus"));
    }

    @Test void productionTransportAndAutomaticAcceptanceAreBlocked() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.SAP_VALIDATION,
                Map.of("suiteJobLeaseApproved", true, "environmentScopeApproved", true, "publishProductionTransport", true)));
        assertEquals(EngineApi.ErrorCode.POLICY_BLOCKED, result.error().errorCode());
        assertEquals(false, result.result().get("financialDifferenceAccepted"));
    }

    @Test void businessProcessTestNeedsSandboxAuthorization() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.BUSINESS_PROCESS_VALIDATION,
                Map.of("suiteJobLeaseApproved", true, "environmentScopeApproved", true)));
        assertEquals(EngineApi.ErrorCode.SUITE_SANDBOX_AUTHORIZATION_REQUIRED, result.error().errorCode());
    }

    @Test void dataMigrationNeedsObjectAndReconciliationAuthorization() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.SUITE_DATA_MIGRATION,
                Map.of("suiteJobLeaseApproved", true, "environmentScopeApproved", true)));
        assertEquals(EngineApi.ErrorCode.SUITE_DATA_MIGRATION_AUTHORIZATION_REQUIRED, result.error().errorCode());
    }

    @Test void productionMutationAndAuthoritySwitchNeedIndependentApproval() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.SUITE_CUTOVER,
                Map.of("suiteJobLeaseApproved", true, "environmentScopeApproved", true, "masterDataAuthoritySwitchRequested", true)));
        assertEquals(EngineApi.ErrorCode.SUITE_PRODUCTION_APPROVAL_REQUIRED, result.error().errorCode());
        assertEquals(false, result.result().get("productionStateChanged"));
    }

    @Test void jobsAreTenantScoped() {
        var response = service.scan(job("tenant-job"));
        assertThrows(IllegalArgumentException.class, () -> service.job("other-org", response.jobId()));
    }

    private static EngineApi.JobRequest job(String key) {
        return new EngineApi.JobRequest("org-1", "snapshot://sha", "workspace://1", "STANDARD", "corr-1", key);
    }
    private static EngineApi.ExecuteStepRequest execute(EngineApi.ExecutorType executor, Map<String,Object> policy) {
        return new EngineApi.ExecuteStepRequest("org-1", "run-1", 1,
                new EngineApi.StepDefinition("step-1", executor, Map.of()),
                "workspace://1", "sha", new EngineApi.ExecutionBudget(60, 60, 1024, 0),
                policy, "corr-1", "exec-" + executor + "-" + policy.hashCode());
    }
}
