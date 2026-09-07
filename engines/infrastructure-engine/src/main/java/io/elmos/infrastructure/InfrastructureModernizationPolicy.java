package io.elmos.infrastructure;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Deterministic Batch 16 policy core. It evaluates supplied facts and never contacts infrastructure. */
public final class InfrastructureModernizationPolicy {
    public String licensedCommercialSoftware(boolean fixedHostId, boolean physicalCpuLicense) {
        return fixedHostId || physicalCpuLicense ? "MODERNIZE_VM_LICENSE_BOUND" : "PLACEMENT_COMPARISON_REQUIRED";
    }

    public List<String> splitSharedVm(Set<String> roles) {
        return roles.stream().sorted().map(role -> "WORKLOAD:" + role).toList();
    }

    public String gracefulShutdown(boolean inFlightCompleted) {
        return inFlightCompleted ? "GRACEFUL_SHUTDOWN_PASS" : "GRACEFUL_SHUTDOWN_GATE_FAILED";
    }

    public String localState(boolean writesLocalUploads, int replicas) {
        return writesLocalUploads && replicas > 1 ? "LOCAL_STATE_RISK" : "STATE_LAYOUT_ACCEPTABLE";
    }

    public String resourceProfile(boolean identicalLimits, boolean utilizationMatches) {
        return identicalLimits && !utilizationMatches ? "RESOURCE_PROFILE_MISMATCH" : "RESOURCE_PROFILE_VALIDATED";
    }

    public String livenessProbe(boolean dependsOnExternalDatabase) {
        return dependsOnExternalDatabase ? "PROBE_SEMANTICS_INVALID" : "PROBE_SEMANTICS_VALID";
    }

    public String networkPolicy(boolean manifestExists, boolean cniEnforces) {
        return manifestExists && cniEnforces ? "NETWORK_POLICY_ENFORCED" : "POLICY_ENFORCEMENT_GATE_FAILED";
    }

    public String disruptionBudget(boolean directDelete, boolean assumedProtected) {
        return directDelete && assumedProtected ? "PDB_PROTECTION_BOUNDARY_MISUNDERSTOOD" : "PDB_SCOPE_DOCUMENTED";
    }

    public String serverlessColdStart(long observedP95Millis, long thresholdMillis) {
        return observedP95Millis > thresholdMillis ? "MIN_INSTANCE_OR_KUBERNETES_REQUIRED" : "COLD_START_GATE_PASS";
    }

    public String serverlessRetry(boolean duplicateDelivery, boolean idempotent) {
        return duplicateDelivery && !idempotent ? "SERVERLESS_IDEMPOTENCY_GATE_FAILED" : "IDEMPOTENCY_VALIDATED";
    }

    public String firstImportPlan(long replaceCount, boolean noChangeBaseline) {
        return replaceCount > 0 && !noChangeBaseline ? "IAC_BASELINE_NOT_ESTABLISHED" : "IAC_BASELINE_READY";
    }

    public String drift(boolean publicPortOpened, boolean declaredInCode) {
        return publicPortOpened && !declaredInCode ? "UNAUTHORIZED_CHANGE" : "DRIFT_RECONCILED";
    }

    public String stateIsolation(String firstOrganization, String secondOrganization, String backendKey) {
        return !Objects.equals(firstOrganization, secondOrganization) && backendKey != null && !backendKey.isBlank()
                ? "CROSS_TENANT_STATE_BLOCKED" : "STATE_SCOPE_VALID";
    }

    public String meshFit(int serviceCount, boolean unifiedMtlsRequired, boolean teamReady) {
        return serviceCount <= 3 && !unifiedMtlsRequired && !teamReady
                ? "GATEWAY_AND_NETWORK_POLICY_RECOMMENDED" : "MESH_EVALUATION_REQUIRED";
    }

    public String ambientMigration(boolean criticalL7Policy, boolean equivalentWaypointReady) {
        return criticalL7Policy && !equivalentWaypointReady ? "AMBIENT_L7_MIGRATION_WINDOW_REQUIRED" : "AMBIENT_POLICY_COMPATIBLE";
    }

    public String traceContinuity(List<String> expectedServices, List<String> observedServices) {
        return observedServices.containsAll(expectedServices) ? "TRACE_CONTINUITY_PASS" : "OBSERVABILITY_GATE_FAILED";
    }

    public String baggage(Set<String> fields) {
        return fields.stream().map(value -> value.toLowerCase(java.util.Locale.ROOT))
                .anyMatch(value -> value.contains("email") || value.contains("secret") || value.contains("token") || value.contains("password"))
                ? "SENSITIVE_BAGGAGE_BLOCKED" : "BAGGAGE_POLICY_PASS";
    }

    public String autoscaling(int desiredReplicas, int databaseMaximumConnections, int connectionsPerReplica) {
        return (long) desiredReplicas * connectionsPerReplica > databaseMaximumConnections
                ? "DOWNSTREAM_CAPACITY_RISK" : "AUTOSCALING_CAPACITY_PASS";
    }

    public String finopsAvailability(int proposedReplicas, int minimumSloReplicas) {
        return proposedReplicas < minimumSloReplicas ? "COST_OPTIMIZATION_REJECTED_SLO" : "COST_OPTIMIZATION_ELIGIBLE";
    }

    public String idleCost(double idleAmount, boolean explicitlyAllocatedOrUnallocated) {
        return idleAmount > 0 && !explicitlyAllocatedOrUnallocated ? "IDLE_COST_COVERAGE_FAILED" : "IDLE_COST_VISIBLE";
    }

    public String backupValidation(boolean backupJobsSucceed, boolean restoreTestPassed) {
        return backupJobsSucceed && restoreTestPassed ? "BACKUP_RESTORE_VALIDATED" : "RESTORE_DRILL_REQUIRED";
    }

    public String zoneDistribution(Set<String> replicaZones, int replicas) {
        return replicas > 1 && replicaZones.size() < 2 ? "TOPOLOGY_GATE_FAILED" : "ZONE_DISTRIBUTION_VALIDATED";
    }

    public String multicloudDecision(boolean lowestCommonOnly, boolean benefitsAndExitCompared) {
        return lowestCommonOnly && !benefitsAndExitCompared ? "PROVIDER_VALUE_AND_EXIT_COMPARISON_REQUIRED" : "MULTICLOUD_TRADEOFF_RECORDED";
    }

    public String exitPlan(boolean proprietaryOnlyExport, boolean intermediateFormatTested) {
        return proprietaryOnlyExport && !intermediateFormatTested ? "PROVIDER_LOCKED" : "EXIT_PLAN_TESTABLE";
    }

    public String dnsCutover(boolean ttlElapsed, boolean oldEndpointCompatible) {
        return ttlElapsed ? "DNS_OBSERVATION_COMPLETE" : oldEndpointCompatible ? "DUAL_ENVIRONMENT_REQUIRED" : "DNS_ROLLBACK_REQUIRED";
    }

    public String decommission(Map<String, Long> legacyConsumers) {
        long traffic = legacyConsumers.values().stream().mapToLong(Long::longValue).sum();
        return traffic == 0 ? "DECOMMISSION_TRAFFIC_GATE_PASS" : "UNKNOWN_CONSUMER_BLOCKS_DECOMMISSION";
    }
}
