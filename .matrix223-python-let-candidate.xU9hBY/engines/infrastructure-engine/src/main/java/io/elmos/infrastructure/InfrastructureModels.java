package io.elmos.infrastructure;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class InfrastructureModels {
    private InfrastructureModels() {}

    public enum ModernizationTrack { VM_MODERNIZATION, CONTAINER_KUBERNETES, SERVERLESS_EVENT_DRIVEN, CLOUD_GOVERNANCE }
    public enum Target {
        KEEP_BARE_METAL, MODERNIZE_VM, CONTAINER_ON_VM, KUBERNETES,
        SERVERLESS_CONTAINER, FUNCTION_AS_A_SERVICE, MANAGED_PLATFORM,
        MANAGED_DATABASE_OR_MIDDLEWARE, EDGE_RUNTIME, RETIRE
    }
    public enum PlacementStatus { RECOMMENDED, FEASIBLE, FEASIBLE_WITH_REFACTOR, PILOT_REQUIRED, NOT_RECOMMENDED, BLOCKED, UNKNOWN }
    public enum RunnerType { INFRASTRUCTURE_DISCOVERY, VM_IMAGE_BUILDER, CONTAINER_BUILD, KUBERNETES_VALIDATION, SERVERLESS_VALIDATION, MULTICLOUD_TEST }
    public enum RunnerStatus { NOT_CONFIGURED, READY }
    public enum ChangeKind { DISCOVERY, PLAN, CREATE, UPDATE, REPLACE, DELETE, IAM, PUBLIC_EXPOSURE, DNS, TRAFFIC, CHAOS, DR_FAILOVER }
    public enum MigrationState {
        DISCOVERY, BASELINING, TARGET_PLANNING, IAC_PREPARING, TARGET_PROVISIONING,
        IMAGE_BUILDING, PLATFORM_CONFIGURING, WORKLOAD_DEPLOYING,
        OBSERVABILITY_CONNECTING, RESILIENCE_VALIDATING, COST_VALIDATING,
        SHADOW_RUNNING, CANARY_RUNNING, TRAFFIC_CUTOVER, STABILITY_HOLD,
        LEGACY_STANDBY, DECOMMISSION_READY, DECOMMISSIONED
    }
    public enum ExceptionState {
        INFRASTRUCTURE_ESTATE_INCOMPLETE, WORKLOAD_PLACEMENT_UNKNOWN, CONTAINERIZATION_BLOCKED,
        KUBERNETES_POLICY_FAILED, SERVERLESS_INELIGIBLE, IAC_IMPORT_INCOMPLETE,
        IAC_DRIFT_DETECTED, NETWORK_CONNECTIVITY_FAILED, OBSERVABILITY_COVERAGE_LOW,
        SLO_FAILED, COST_THRESHOLD_EXCEEDED, RESILIENCE_TEST_FAILED,
        MULTICLOUD_PORTABILITY_BLOCKED, CUTOVER_PAUSED, ROLLBACK_REQUIRED, DECOMMISSION_BLOCKED
    }
    public enum EvidenceType {
        INFRASTRUCTURE_ESTATE, WORKLOAD_PLACEMENT, CONTAINER_BUILD, CONTAINER_SUPPLY_CHAIN,
        KUBERNETES_PLATFORM, KUBERNETES_WORKLOAD, SERVERLESS_PROFILE, IAC_PLAN, IAC_APPLY,
        IAC_DRIFT, NETWORK_TOPOLOGY, SERVICE_MESH, OBSERVABILITY_PROFILE, SLO_RESULT,
        COST_ALLOCATION, COST_OPTIMIZATION, RESILIENCE_RESULT, BACKUP_RESTORE, DR_TEST,
        MULTICLOUD_PORTABILITY, INFRASTRUCTURE_CUTOVER, INFRASTRUCTURE_DECOMMISSION
    }
    public enum CostUnit {
        INFRA_DISCOVERY_UNIT, VM_IMAGE_BUILD, CONTAINER_BUILD, KUBERNETES_CLUSTER_HOUR,
        SERVERLESS_VALIDATION, IAC_RESOURCE_PLAN, IAC_APPLY, OBSERVABILITY_GB,
        CHAOS_EXPERIMENT, DR_TEST, MULTICLOUD_TEST, CUTOVER_OPERATION
    }

    public record RunnerProfile(
            RunnerType type,
            List<String> tools,
            Set<String> discoveryPermissions,
            Set<ChangeKind> changeCapabilities,
            boolean namedApprovalRequired,
            RunnerStatus status) {
        public RunnerProfile {
            Objects.requireNonNull(type); tools = List.copyOf(tools);
            discoveryPermissions = Set.copyOf(discoveryPermissions);
            changeCapabilities = Set.copyOf(changeCapabilities);
            Objects.requireNonNull(status);
            if (discoveryPermissions.stream().anyMatch(InfrastructureModels::writeLike)) {
                throw new IllegalArgumentException("discovery permissions must be read only");
            }
            if (!changeCapabilities.isEmpty() && !namedApprovalRequired) {
                throw new IllegalArgumentException("infrastructure changes require named approval");
            }
        }
    }

    public record WorkloadProfile(
            String workloadId,
            boolean fixedHostIdentity,
            boolean physicalCpuLicense,
            boolean hardwareOrKernelBound,
            boolean stateExternalized,
            boolean eventDriven,
            long maximumDurationSeconds,
            boolean latencySensitive,
            boolean kubernetesTeamReady,
            boolean highReleaseFrequency,
            boolean multiService,
            boolean stableLowChange,
            List<String> evidenceRefs) {
        public WorkloadProfile {
            require(workloadId, "workloadId");
            if (maximumDurationSeconds < 0) throw new IllegalArgumentException("maximumDurationSeconds cannot be negative");
            evidenceRefs = List.copyOf(Objects.requireNonNull(evidenceRefs));
        }
    }

    public record PlacementCandidate(
            Target target,
            PlacementStatus status,
            int score,
            List<String> reasonCodes,
            List<String> requiredGates) {
        public PlacementCandidate {
            Objects.requireNonNull(target); Objects.requireNonNull(status);
            if (score < 0 || score > 100) throw new IllegalArgumentException("score must be between 0 and 100");
            reasonCodes = List.copyOf(reasonCodes); requiredGates = List.copyOf(requiredGates);
        }
    }

    public record ChangePlan(
            String organizationId,
            String planRef,
            String stateVersion,
            ChangeKind changeKind,
            boolean policyPassed,
            boolean securityPassed,
            boolean costPassed,
            String rollbackRef,
            String approvedBy,
            List<String> evidenceRefs,
            Map<String, String> providerBindings) {
        public ChangePlan {
            require(organizationId, "organizationId"); require(planRef, "planRef");
            require(stateVersion, "stateVersion"); Objects.requireNonNull(changeKind);
            evidenceRefs = List.copyOf(evidenceRefs); providerBindings = Map.copyOf(providerBindings);
        }
    }

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static boolean writeLike(String permission) {
        String normalized = permission.toUpperCase(java.util.Locale.ROOT);
        return normalized.contains("WRITE") || normalized.contains("CREATE")
                || normalized.contains("UPDATE") || normalized.contains("DELETE")
                || normalized.contains("ADMIN") || normalized.contains("APPLY");
    }
}
