package io.elmos.infrastructure;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;

class Batch16AcceptanceScenariosTest {
    private final InfrastructureModernizationPolicy policy = new InfrastructureModernizationPolicy();

    @Test void scenario01_licenseBoundSoftwareStaysOnModernVm() {
        assertEquals("MODERNIZE_VM_LICENSE_BOUND", policy.licensedCommercialSoftware(true, true));
    }
    @Test void scenario02_sharedVmBecomesFourLogicalWorkloads() {
        assertEquals(4, policy.splitSharedVm(Set.of("WEB", "BATCH", "SCHEDULER", "FILE")).size());
    }
    @Test void scenario03_ignoredSigtermBlocksKubernetesCanary() {
        assertEquals("GRACEFUL_SHUTDOWN_GATE_FAILED", policy.gracefulShutdown(false));
    }
    @Test void scenario04_localUploadsBlockReplicaScale() {
        assertEquals("LOCAL_STATE_RISK", policy.localState(true, 3));
    }
    @Test void scenario05_uniformLimitsDoNotReplaceProfiles() {
        assertEquals("RESOURCE_PROFILE_MISMATCH", policy.resourceProfile(true, false));
    }
    @Test void scenario06_databaseDependentLivenessIsInvalid() {
        assertEquals("PROBE_SEMANTICS_INVALID", policy.livenessProbe(true));
    }
    @Test void scenario07_manifestWithoutCniEnforcementFails() {
        assertEquals("POLICY_ENFORCEMENT_GATE_FAILED", policy.networkPolicy(true, false));
    }
    @Test void scenario08_pdbDoesNotBlockDirectDeletion() {
        assertEquals("PDB_PROTECTION_BOUNDARY_MISUNDERSTOOD", policy.disruptionBudget(true, true));
    }
    @Test void scenario09_coldStartAboveSloRequiresWarmCapacityOrKubernetes() {
        assertEquals("MIN_INSTANCE_OR_KUBERNETES_REQUIRED", policy.serverlessColdStart(1500, 300));
    }
    @Test void scenario10_retryWithoutIdempotencyFails() {
        assertEquals("SERVERLESS_IDEMPOTENCY_GATE_FAILED", policy.serverlessRetry(true, false));
    }
    @Test void scenario11_firstImportCannotReplaceCoreSubnet() {
        assertEquals("IAC_BASELINE_NOT_ESTABLISHED", policy.firstImportPlan(4, false));
    }
    @Test void scenario12_manualPublicPortIsUnauthorizedDrift() {
        assertEquals("UNAUTHORIZED_CHANGE", policy.drift(true, false));
    }
    @Test void scenario13_crossTenantStateIsBlocked() {
        assertEquals("CROSS_TENANT_STATE_BLOCKED", policy.stateIsolation("org-a", "org-b", "shared/network.tfstate"));
    }
    @Test void scenario14_smallSystemDoesNotNeedMesh() {
        assertEquals("GATEWAY_AND_NETWORK_POLICY_RECOMMENDED", policy.meshFit(3, false, false));
    }
    @Test void scenario15_ambientL7MigrationNeedsWindow() {
        assertEquals("AMBIENT_L7_MIGRATION_WINDOW_REQUIRED", policy.ambientMigration(true, false));
    }
    @Test void scenario16_crossLanguageTraceBreakFailsObservability() {
        assertEquals("OBSERVABILITY_GATE_FAILED", policy.traceContinuity(
                List.of("java", "dotnet", "python"), List.of("java", "python")));
    }
    @Test void scenario17_sensitiveBaggageIsBlocked() {
        assertEquals("SENSITIVE_BAGGAGE_BLOCKED", policy.baggage(Set.of("trace-hint", "user-email")));
    }
    @Test void scenario18_hpaCannotExhaustDatabaseConnections() {
        assertEquals("DOWNSTREAM_CAPACITY_RISK", policy.autoscaling(100, 500, 10));
    }
    @Test void scenario19_finopsCannotBreakSlo() {
        assertEquals("COST_OPTIMIZATION_REJECTED_SLO", policy.finopsAvailability(1, 3));
    }
    @Test void scenario20_idleCostCannotDisappear() {
        assertEquals("IDLE_COST_COVERAGE_FAILED", policy.idleCost(1000, false));
    }
    @Test void scenario21_backupWithoutRestoreIsNotValidated() {
        assertEquals("RESTORE_DRILL_REQUIRED", policy.backupValidation(true, false));
    }
    @Test void scenario22_singleZoneReplicaSetFailsTopology() {
        assertEquals("TOPOLOGY_GATE_FAILED", policy.zoneDistribution(Set.of("zone-a"), 3));
    }
    @Test void scenario23_multicloudIsNotLowestCommonDenominator() {
        assertEquals("PROVIDER_VALUE_AND_EXIT_COMPARISON_REQUIRED", policy.multicloudDecision(true, false));
    }
    @Test void scenario24_proprietaryOnlyExportIsProviderLocked() {
        assertEquals("PROVIDER_LOCKED", policy.exitPlan(true, false));
    }
    @Test void scenario25_dnsRequiresDualEnvironmentDuringTtlWindow() {
        assertEquals("DUAL_ENVIRONMENT_REQUIRED", policy.dnsCutover(false, true));
    }
    @Test void scenario26_unknownLegacyConsumerBlocksDecommission() {
        assertEquals("UNKNOWN_CONSUMER_BLOCKS_DECOMMISSION", policy.decommission(Map.of("internal-batch", 1L)));
    }
}
