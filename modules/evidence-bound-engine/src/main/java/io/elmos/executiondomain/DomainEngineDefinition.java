package io.elmos.executiondomain;

import io.elmos.engine.api.EngineApi.ErrorCode;
import io.elmos.engine.api.EngineApi.ExecutorType;

import java.util.List;
import java.util.Map;
import java.util.Set;

public record DomainEngineDefinition(
        String engineName,
        List<String> domainKinds,
        List<String> targetProfiles,
        List<String> artifactKinds,
        List<String> projectFormats,
        List<String> runnerProfiles,
        List<String> adapters,
        List<String> validationCapabilities,
        Map<String, List<String>> stateMachines,
        Set<String> exceptionStates,
        Set<ExecutorType> executors,
        Map<ExecutorType, AuthorizationRule> authorizationRules,
        Set<String> prohibitedPolicyKeys,
        ErrorCode runnerRequired,
        ErrorCode leaseRequired,
        ErrorCode estateIncomplete,
        ErrorCode productionApprovalRequired) {

    public DomainEngineDefinition {
        domainKinds = List.copyOf(domainKinds);
        targetProfiles = List.copyOf(targetProfiles);
        artifactKinds = List.copyOf(artifactKinds);
        projectFormats = List.copyOf(projectFormats);
        runnerProfiles = List.copyOf(runnerProfiles);
        adapters = List.copyOf(adapters);
        validationCapabilities = List.copyOf(validationCapabilities);
        stateMachines = stateMachines.entrySet().stream().collect(java.util.stream.Collectors.toUnmodifiableMap(
                Map.Entry::getKey, entry -> List.copyOf(entry.getValue())));
        exceptionStates = Set.copyOf(exceptionStates);
        executors = Set.copyOf(executors);
        authorizationRules = Map.copyOf(authorizationRules);
        prohibitedPolicyKeys = Set.copyOf(prohibitedPolicyKeys);
    }

    public record AuthorizationRule(String policyKey, ErrorCode errorCode, String message) {}
}
