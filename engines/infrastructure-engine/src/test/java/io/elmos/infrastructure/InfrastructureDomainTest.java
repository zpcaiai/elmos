package io.elmos.infrastructure;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.infrastructure.InfrastructureModels.*;
import static org.junit.jupiter.api.Assertions.*;

class InfrastructureDomainTest {
    @Test void fixedHostLicenseNeverDefaultsToKubernetes() {
        var profile = new WorkloadProfile("vendor", true, true, false, false, false,
                0, false, true, true, true, false, List.of("evidence:license"));
        var candidates = new WorkloadPlacementPlanner().candidates(profile);
        assertEquals(Target.MODERNIZE_VM, candidates.getFirst().target());
        assertEquals(PlacementStatus.NOT_RECOMMENDED,
                candidates.stream().filter(value -> value.target() == Target.KUBERNETES).findFirst().orElseThrow().status());
    }

    @Test void serverlessRequiresBoundedStatelessWorkload() {
        var profile = new WorkloadProfile("event", false, false, false, true, true,
                60, false, false, false, false, false, List.of("evidence:runtime"));
        assertEquals(Target.SERVERLESS_CONTAINER, new WorkloadPlacementPlanner().candidates(profile).getFirst().target());
    }

    @Test void changeGateRequiresAllEvidenceAndNamedApproval() {
        var plan = new ChangePlan("org-1", "sha256:plan", "state-7", ChangeKind.TRAFFIC,
                true, true, true, "sha256:rollback", null, List.of("evidence:network"), Map.of());
        var decision = new InfrastructureChangeGate().evaluate(plan);
        assertFalse(decision.allowed());
        assertTrue(decision.blockers().contains("NAMED_INFRASTRUCTURE_APPROVAL_REQUIRED"));
    }

    @Test void lifecycleCannotSkipCanary() {
        assertThrows(IllegalStateException.class,
                () -> new InfrastructureLifecycle().advance(MigrationState.SHADOW_RUNNING, MigrationState.TRAFFIC_CUTOVER));
    }

    @Test void runnerDiscoveryPermissionsCannotContainWrites() {
        assertThrows(IllegalArgumentException.class, () -> new RunnerProfile(
                RunnerType.INFRASTRUCTURE_DISCOVERY, List.of("cloud"), Set.of("WRITE_NETWORK"),
                Set.of(), true, RunnerStatus.NOT_CONFIGURED));
    }

    @Test void evidenceMapsIntoSharedScopeAndCost() {
        var mapping = new InfrastructureEvidenceMapper().map(EvidenceType.BACKUP_RESTORE);
        assertEquals("CLOUD_INFRASTRUCTURE", mapping.scope());
        assertEquals("ELMOS / Restore", mapping.check());
        assertEquals("DR_TEST", mapping.costUnit());
    }
}
