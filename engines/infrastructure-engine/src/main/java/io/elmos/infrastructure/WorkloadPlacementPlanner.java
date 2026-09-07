package io.elmos.infrastructure;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static io.elmos.infrastructure.InfrastructureModels.*;

public final class WorkloadPlacementPlanner {
    public List<PlacementCandidate> candidates(WorkloadProfile profile) {
        var candidates = new ArrayList<PlacementCandidate>();
        if (profile.fixedHostIdentity() || profile.physicalCpuLicense()) {
            candidates.add(candidate(Target.MODERNIZE_VM, PlacementStatus.RECOMMENDED, 90,
                    List.of("FIXED_HOST_OR_PHYSICAL_CPU_LICENSE"), List.of("LICENSE_VALIDATION", "IMAGE_HARDENING")));
            candidates.add(candidate(Target.KUBERNETES, PlacementStatus.NOT_RECOMMENDED, 5,
                    List.of("LICENSE_BINDING"), List.of("VENDOR_APPROVAL")));
            return sorted(candidates);
        }
        if (profile.hardwareOrKernelBound()) {
            candidates.add(candidate(Target.KEEP_BARE_METAL, PlacementStatus.FEASIBLE, 82,
                    List.of("HARDWARE_OR_KERNEL_BOUND"), List.of("HOST_HARDENING", "BACKUP_RESTORE")));
            candidates.add(candidate(Target.MODERNIZE_VM, PlacementStatus.PILOT_REQUIRED, 58,
                    List.of("DEVICE_COMPATIBILITY_UNKNOWN"), List.of("HARDWARE_PILOT")));
        }
        if (profile.eventDriven() && profile.stateExternalized() && profile.maximumDurationSeconds() <= 900 && !profile.latencySensitive()) {
            candidates.add(candidate(Target.SERVERLESS_CONTAINER, PlacementStatus.RECOMMENDED, 88,
                    List.of("EVENT_DRIVEN", "BOUNDED_DURATION", "STATE_EXTERNALIZED"),
                    List.of("COLD_START", "IDEMPOTENCY", "DLQ", "COST")));
            candidates.add(candidate(Target.FUNCTION_AS_A_SERVICE, PlacementStatus.FEASIBLE, 80,
                    List.of("EVENT_DRIVEN"), List.of("EVENT_CONTRACT", "CONCURRENCY")));
        }
        if (profile.kubernetesTeamReady() && profile.highReleaseFrequency() && profile.multiService()) {
            candidates.add(candidate(Target.KUBERNETES, PlacementStatus.RECOMMENDED, 86,
                    List.of("PLATFORM_READY", "MULTI_SERVICE", "HIGH_RELEASE_FREQUENCY"),
                    List.of("PLATFORM_POLICY", "NETWORK_ENFORCEMENT", "SLO", "RESTORE")));
        } else {
            candidates.add(candidate(Target.KUBERNETES, PlacementStatus.NOT_RECOMMENDED, 38,
                    List.of("TEAM_OR_WORKLOAD_FIT_LOW"), List.of("PLATFORM_READINESS")));
        }
        if (profile.stableLowChange()) {
            candidates.add(candidate(Target.MODERNIZE_VM, PlacementStatus.FEASIBLE, 72,
                    List.of("STABLE_LOW_CHANGE"), List.of("IMAGE_HARDENING", "OBSERVABILITY")));
        }
        if (candidates.isEmpty()) {
            candidates.add(candidate(Target.CONTAINER_ON_VM, PlacementStatus.PILOT_REQUIRED, 55,
                    List.of("EVIDENCE_INCOMPLETE"), List.of("CONTAINER_PILOT", "STATE_CLASSIFICATION")));
        }
        return sorted(candidates);
    }

    private PlacementCandidate candidate(Target target, PlacementStatus status, int score,
                                         List<String> reasons, List<String> gates) {
        return new PlacementCandidate(target, status, score, reasons, gates);
    }

    private List<PlacementCandidate> sorted(List<PlacementCandidate> values) {
        return values.stream().sorted(Comparator.comparingInt(PlacementCandidate::score).reversed()
                .thenComparing(value -> value.target().name())).toList();
    }
}
