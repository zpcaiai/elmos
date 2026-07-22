package io.elmos.executiondomain;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class EvidenceBoundDomainEngineTest {
    private final EvidenceBoundDomainEngine engine = new EvidenceBoundDomainEngine(new DomainEngineDefinition(
            "ELMOS_TEST_DOMAIN", List.of("TEST"), List.of("MODERN"), List.of("BUNDLE"), List.of("ESTATE"),
            List.of("RUNNER"), List.of("ADAPTER"), List.of("GATE"), Map.of("DEFAULT", List.of("DISCOVER", "PLAN", "VALIDATE")), Set.of("BLOCKED"),
            Set.of(EngineApi.ExecutorType.SCANNER), Map.of(),
            Set.of("destructive"), EngineApi.ErrorCode.WORKSPACE_UNAVAILABLE,
            EngineApi.ErrorCode.HUMAN_REVIEW_REQUIRED, EngineApi.ErrorCode.VALIDATION_FAILED,
            EngineApi.ErrorCode.POLICY_BLOCKED));

    @Test void discoveryAndExecutionFailClosedWithoutFabricatedEvidence() {
        var request = new EngineApi.JobRequest("org", "snapshot", "workspace", "DEFAULT", "corr", "key");
        var discovered = engine.discover(request);
        assertEquals(EngineApi.ErrorCode.WORKSPACE_UNAVAILABLE, discovered.error().errorCode());
        assertTrue(discovered.evidenceRefs().isEmpty());
        var execute = new EngineApi.ExecuteStepRequest("org", "run", 1,
                new EngineApi.StepDefinition("step", EngineApi.ExecutorType.SCANNER, Map.of()),
                "workspace", "sha", new EngineApi.ExecutionBudget(1, 1, 1, 0), Map.of(), "corr", "execute");
        assertEquals(EngineApi.ErrorCode.HUMAN_REVIEW_REQUIRED, engine.executeStep(execute).error().errorCode());
        assertEquals(false, discovered.result().get("evidenceFabricated"));
    }

    static List<DomainEngineDefinition> domainDefinitions() {
        return List.of(DomainDefinitions.softwareDelivery(), DomainDefinitions.aiPlatform(),
                DomainDefinitions.industrial(), DomainDefinitions.operations(),
                DomainDefinitions.enterpriseArchitecture());
    }

    @ParameterizedTest @MethodSource("domainDefinitions")
    void everyDomainPublishesFailClosedCapabilities(DomainEngineDefinition definition) {
        var capabilities = new EvidenceBoundDomainEngine(definition).capabilities();
        assertEquals(definition.engineName(), capabilities.engineName());
        assertEquals(false, capabilities.sandboxRequirements().get("controlPlaneExecution"));
        assertEquals("DENY", capabilities.sandboxRequirements().get("productionMutationDefault"));
        assertEquals(false, capabilities.sandboxRequirements().get("humanDecisionAutoGrant"));
        @SuppressWarnings("unchecked") Map<String, String> adapters =
                (Map<String, String>) capabilities.sandboxRequirements().get("adapterStatus");
        assertEquals(definition.adapters().size(), adapters.size());
        assertTrue(adapters.values().stream().allMatch("NOT_CONFIGURED"::equals));
    }

    @ParameterizedTest @MethodSource("domainDefinitions")
    void everyDomainRejectsMissingRunnerLeaseAndProhibitedOperations(DomainEngineDefinition definition) {
        var domain = new EvidenceBoundDomainEngine(definition);
        var discovery = domain.discover(job("discover-" + definition.engineName()));
        assertEquals(definition.runnerRequired(), discovery.error().errorCode());
        var executor = definition.executors().iterator().next();
        var missingLease = domain.executeStep(execute(executor, Map.of(), "lease-" + definition.engineName()));
        assertEquals(definition.leaseRequired(), missingLease.error().errorCode());
        var prohibited = domain.executeStep(execute(executor,
                Map.of("jobLeaseApproved", true, "environmentScopeApproved", true,
                        definition.prohibitedPolicyKeys().iterator().next(), true),
                "prohibited-" + definition.engineName()));
        assertEquals(EngineApi.ErrorCode.POLICY_BLOCKED, prohibited.error().errorCode());
        assertEquals(false, prohibited.result().get("externalOperationExecuted"));
        assertEquals(false, prohibited.result().get("productionStateChanged"));
    }

    @ParameterizedTest @MethodSource("domainDefinitions")
    void dedicatedAuthorizationCanNeverBecomeSyntheticSuccess(DomainEngineDefinition definition) {
        var domain = new EvidenceBoundDomainEngine(definition);
        definition.authorizationRules().forEach((executor, rule) -> {
            var absent = domain.execute("authorization", execute(executor,
                    Map.of("jobLeaseApproved", true, "environmentScopeApproved", true),
                    "auth-missing-" + executor));
            assertEquals(rule.errorCode(), absent.error().errorCode());
            var approved = domain.execute("authorization-approved", execute(executor,
                    Map.of("jobLeaseApproved", true, "environmentScopeApproved", true, rule.policyKey(), true),
                    "auth-approved-" + executor));
            assertEquals(definition.runnerRequired(), approved.error().errorCode());
            assertEquals(EngineApi.JobStatus.FAILED, approved.status());
        });
    }

    @ParameterizedTest @MethodSource("domainDefinitions")
    void jobIdsAreTenantScopedAndRequestsAreIdempotent(DomainEngineDefinition definition) {
        var domain = new EvidenceBoundDomainEngine(definition);
        var request = job("idempotent-" + definition.engineName());
        var first = domain.discover(request);
        assertEquals(first, domain.discover(request));
        assertThrows(IllegalArgumentException.class, () -> domain.job("another-org", first.jobId()));
        assertEquals(EngineApi.JobStatus.CANCELLED, domain.cancel("org", first.jobId()).status());
    }

    @ParameterizedTest @MethodSource("domainDefinitions")
    void lifecycleTransitionsAreSequentialAndExceptionStatesAreTerminal(DomainEngineDefinition definition) {
        var domain = new EvidenceBoundDomainEngine(definition);
        definition.stateMachines().forEach((machine, states) -> {
            assertTrue(states.size() >= 2);
            for (int index = 0; index < states.size() - 1; index++) {
                assertTrue(domain.transitionAllowed(machine, states.get(index), states.get(index + 1)));
            }
            if (states.size() >= 3) assertFalse(domain.transitionAllowed(machine, states.getFirst(), states.get(2)));
            assertFalse(domain.transitionAllowed(machine, states.getLast(), states.getFirst()));
            assertFalse(domain.transitionAllowed(machine, definition.exceptionStates().iterator().next(), states.getFirst()));
        });
    }

    private static EngineApi.JobRequest job(String key) {
        return new EngineApi.JobRequest("org", "snapshot", "workspace", "DEFAULT", "corr", key);
    }

    private static EngineApi.ExecuteStepRequest execute(EngineApi.ExecutorType executor, Map<String, Object> policy, String key) {
        return new EngineApi.ExecuteStepRequest("org", "run", 1,
                new EngineApi.StepDefinition("step", executor, Map.of()), "workspace", "sha",
                new EngineApi.ExecutionBudget(60, 60, 1024, 1), policy, "corr", key);
    }
}
