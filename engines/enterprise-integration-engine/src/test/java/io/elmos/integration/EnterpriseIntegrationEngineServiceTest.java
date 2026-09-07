package io.elmos.integration;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class EnterpriseIntegrationEngineServiceTest {
    private final EnterpriseIntegrationEngineService service = new EnterpriseIntegrationEngineService();

    @Test void capabilitiesAreMultiPlatformAndFailClosed() {
        var c = service.capabilities();
        assertEquals("ELMOS_ENTERPRISE_INTEGRATION", c.engineName());
        assertTrue(c.languages().contains("IBM_MQ"));
        assertTrue(c.languages().contains("KAFKA"));
        assertTrue(c.languages().contains("RABBITMQ"));
        assertEquals(false, c.sandboxRequirements().get("controlPlaneExecution"));
        assertEquals("DENY", c.sandboxRequirements().get("productionMutationDefault"));
    }

    @Test void discoveryDoesNotFabricateEvidenceWithoutAdapter() {
        var result = service.scan(job("scan-1"));
        assertEquals(EngineApi.JobStatus.FAILED, result.status());
        assertEquals(EngineApi.ErrorCode.INTEGRATION_RUNNER_REQUIRED, result.error().errorCode());
        assertTrue(result.evidenceRefs().isEmpty());
        assertEquals(false, result.result().get("evidenceFabricated"));
    }

    @Test void executeRequiresLeaseAndResourceScope() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.BROKER_VALIDATION, Map.of()));
        assertEquals(EngineApi.ErrorCode.INTEGRATION_LEASE_REQUIRED, result.error().errorCode());
        assertEquals("NOT_RUN", result.result().get("externalStatus"));
    }

    @Test void destructiveBrokerAndCutoverActionsAreAlwaysBlocked() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.BROKER_VALIDATION,
                Map.of("integrationJobLeaseApproved", true, "resourceScopeApproved", true, "resetProductionOffset", true)));
        assertEquals(EngineApi.ErrorCode.POLICY_BLOCKED, result.error().errorCode());
        assertEquals(false, result.result().get("messageLossAccepted"));
    }

    @Test void partnerTestNeedsPartnerAuthorization() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.B2B_VALIDATION,
                Map.of("integrationJobLeaseApproved", true, "resourceScopeApproved", true)));
        assertEquals(EngineApi.ErrorCode.PARTNER_TEST_AUTHORIZATION_REQUIRED, result.error().errorCode());
    }

    @Test void replayNeedsRangeAndSideEffectAuthorization() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.INTEGRATION_REPLAY,
                Map.of("integrationJobLeaseApproved", true, "resourceScopeApproved", true)));
        assertEquals(EngineApi.ErrorCode.MESSAGE_REPLAY_NOT_AUTHORIZED, result.error().errorCode());
    }

    @Test void productionMutationNeedsIndependentApproval() {
        var result = service.executeStep(execute(EngineApi.ExecutorType.API_GATEWAY_VALIDATION,
                Map.of("integrationJobLeaseApproved", true, "resourceScopeApproved", true, "productionMutationRequested", true)));
        assertEquals(EngineApi.ErrorCode.INTEGRATION_PRODUCTION_APPROVAL_REQUIRED, result.error().errorCode());
        assertEquals(false, result.result().get("productionStateChanged"));
    }

    @Test void jobsAreTenantScoped() {
        var response = service.scan(job("tenant-job"));
        assertThrows(EngineApi.IdempotencyConflictException.class, () -> service.scan(
                new EngineApi.JobRequest("org-1", "snapshot://changed", "workspace://1", "STANDARD", "corr-2", "tenant-job")));
        assertThrows(EngineApi.JobNotFoundException.class, () -> service.job("other-org", response.jobId()));
        assertThrows(EngineApi.JobConflictException.class, () -> service.cancel("org-1", response.jobId()));
        assertEquals(response, service.job("org-1", response.jobId()));
        assertEquals(response, service.scan(job("tenant-job")));
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
