package io.elmos.portfolio;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class PortfolioScaleModels {
    private PortfolioScaleModels() {}

    public enum Criticality { P0, P1, P2, P3 }
    public enum RepositoryStatus { ACTIVE, ARCHIVED, MIRROR, FORK, SHADOW, INACCESSIBLE, DELETED }
    public enum TaskStatus { SUCCEEDED, FAILED }
    public enum CampaignStatus { READY, BLOCKED }

    public record RepositoryAsset(String id, String tenantId, String owner, Set<String> regions,
                                  Set<String> toolchains, long loc, RepositoryStatus status,
                                  Criticality criticality, List<String> evidenceRefs) {
        public RepositoryAsset {
            requireText(id, "repository id");
            requireText(tenantId, "tenant id");
            requireText(owner, "repository owner");
            regions = Set.copyOf(regions);
            toolchains = Set.copyOf(toolchains);
            evidenceRefs = List.copyOf(evidenceRefs);
            Objects.requireNonNull(status, "repository status");
            Objects.requireNonNull(criticality, "repository criticality");
            if (regions.isEmpty() || toolchains.isEmpty() || loc < 0) {
                throw new IllegalArgumentException("repository placement, toolchain and LOC must be explicit");
            }
        }
    }

    public record UnreachableAsset(String logicalKey, String reason, String owner) {
        public UnreachableAsset {
            requireText(logicalKey, "unreachable logical key");
            requireText(reason, "unreachable reason");
            requireText(owner, "unreachable owner");
        }
    }

    public record Dependency(String id, String fromRepositoryId, String toRepositoryId,
                             String kind, Criticality criticality, double confidence,
                             List<String> evidenceRefs) {
        public Dependency {
            requireText(id, "dependency id");
            requireText(fromRepositoryId, "dependency source");
            requireText(toRepositoryId, "dependency target");
            requireText(kind, "dependency kind");
            Objects.requireNonNull(criticality, "dependency criticality");
            evidenceRefs = List.copyOf(evidenceRefs);
            if (fromRepositoryId.equals(toRepositoryId) || confidence < 0 || confidence > 1) {
                throw new IllegalArgumentException("invalid dependency");
            }
        }
    }

    public record PortfolioSnapshot(String snapshotId, String digest, int expectedRepositoryCount,
                                    List<RepositoryAsset> repositories,
                                    List<UnreachableAsset> unreachable,
                                    List<Dependency> dependencies) {
        public PortfolioSnapshot {
            requireText(snapshotId, "snapshot id");
            requireText(digest, "snapshot digest");
            repositories = List.copyOf(repositories);
            unreachable = List.copyOf(unreachable);
            dependencies = List.copyOf(dependencies);
            if (expectedRepositoryCount < 1 || repositories.size() + unreachable.size() > expectedRepositoryCount) {
                throw new IllegalArgumentException("invalid expected repository count");
            }
            Set<String> ids = uniqueIds(repositories.stream().map(RepositoryAsset::id).toList(), "repository");
            uniqueIds(unreachable.stream().map(UnreachableAsset::logicalKey).toList(), "unreachable repository");
            uniqueIds(dependencies.stream().map(Dependency::id).toList(), "dependency");
            for (Dependency edge : dependencies) {
                if (!ids.contains(edge.fromRepositoryId()) || !ids.contains(edge.toRepositoryId())) {
                    throw new IllegalArgumentException("dependency references unknown repository: " + edge.id());
                }
            }
        }
    }

    public record WorkUnit(String id, String tenantId, String owner, String repositoryId,
                           Set<String> regions, String toolchain, long estimatedLoc,
                           Criticality criticality, List<String> dependsOn,
                           String partitionKey, List<String> evidenceRefs) {
        public WorkUnit {
            requireText(id, "work-unit id");
            requireText(tenantId, "work-unit tenant");
            requireText(owner, "work-unit owner");
            requireText(repositoryId, "work-unit repository");
            requireText(toolchain, "work-unit toolchain");
            requireText(partitionKey, "work-unit partition key");
            regions = Set.copyOf(regions);
            dependsOn = List.copyOf(dependsOn);
            evidenceRefs = List.copyOf(evidenceRefs);
            Objects.requireNonNull(criticality, "work-unit criticality");
            if (regions.isEmpty() || estimatedLoc < 0) throw new IllegalArgumentException("invalid work-unit constraints");
        }
    }

    public record PlanningResult(List<WorkUnit> workUnits, double inventoryCoverage,
                                 List<String> blockers) {
        public PlanningResult {
            workUnits = List.copyOf(workUnits);
            blockers = List.copyOf(blockers);
        }
        public boolean executable() { return blockers.isEmpty(); }
    }

    public record Runner(String id, String tenantId, String region, boolean attested,
                         Set<String> toolchains, long maximumLoc) {
        public Runner {
            requireText(id, "runner id");
            requireText(tenantId, "runner tenant");
            requireText(region, "runner region");
            toolchains = Set.copyOf(toolchains);
            if (toolchains.isEmpty() || maximumLoc < 1) throw new IllegalArgumentException("invalid runner capacity");
        }
    }

    public record Assignment(String workUnitId, String runnerId) {}
    public record SchedulingResult(List<Assignment> assignments, List<String> unscheduledWorkUnitIds) {
        public SchedulingResult {
            assignments = List.copyOf(assignments);
            unscheduledWorkUnitIds = List.copyOf(unscheduledWorkUnitIds);
        }
        public boolean complete() { return unscheduledWorkUnitIds.isEmpty(); }
    }

    public record TaskRequest(String taskId, String tenantId, String workUnitId,
                              String idempotencyKey, String inputDigest, int maximumAttempts,
                              boolean externalEffectRequested) {
        public TaskRequest {
            requireText(taskId, "task id");
            requireText(tenantId, "task tenant");
            requireText(workUnitId, "task work unit");
            requireText(idempotencyKey, "idempotency key");
            requireText(inputDigest, "input digest");
            if (maximumAttempts < 1 || maximumAttempts > 10) throw new IllegalArgumentException("maximum attempts must be between 1 and 10");
        }
    }

    public record Checkpoint(String taskId, int attempt, String stateDigest, String lastFailure) {
        public Checkpoint { requireText(taskId, "checkpoint task id"); requireText(stateDigest, "checkpoint state digest"); }
    }

    public record TaskOutcome(TaskStatus status, int attempts, boolean replayed,
                              boolean externalEffectApplied, String commitToken,
                              String outputDigest, List<String> failures) {
        public TaskOutcome {
            Objects.requireNonNull(status, "task status");
            failures = List.copyOf(failures);
        }
    }

    public record ActivityResult(boolean succeeded, String stateDigest, String outputDigest, String failureCode) {
        public ActivityResult {
            requireText(stateDigest, "activity state digest");
            if (succeeded) requireText(outputDigest, "activity output digest");
            if (!succeeded) requireText(failureCode, "activity failure code");
        }
        public static ActivityResult success(String stateDigest, String outputDigest) {
            return new ActivityResult(true, stateDigest, outputDigest, null);
        }
        public static ActivityResult failure(String stateDigest, String failureCode) {
            return new ActivityResult(false, stateDigest, null, failureCode);
        }
    }

    public record WorkflowSnapshot(Map<String, String> requestFingerprints,
                                   Map<String, TaskOutcome> outcomes,
                                   Map<String, Checkpoint> checkpoints,
                                   Set<String> committedTokens) {
        public WorkflowSnapshot {
            requestFingerprints = Map.copyOf(requestFingerprints);
            outcomes = Map.copyOf(outcomes);
            checkpoints = Map.copyOf(checkpoints);
            committedTokens = Set.copyOf(committedTokens);
        }
    }

    public record Campaign(String id, List<WorkUnit> workUnits, int maximumParallel,
                           long budgetUnits, Set<String> requiredApprovals,
                           Set<String> grantedApprovals) {
        public Campaign {
            requireText(id, "campaign id");
            workUnits = List.copyOf(workUnits);
            requiredApprovals = Set.copyOf(requiredApprovals);
            grantedApprovals = Set.copyOf(grantedApprovals);
            if (maximumParallel < 1 || budgetUnits < 0) throw new IllegalArgumentException("invalid campaign bounds");
        }
    }

    public record CampaignDecision(CampaignStatus status, List<List<String>> waves,
                                   long estimatedCostUnits, List<String> blockers) {
        public CampaignDecision {
            Objects.requireNonNull(status, "campaign status");
            waves = waves.stream().map(List::copyOf).toList();
            blockers = List.copyOf(blockers);
        }
    }

    static void requireText(String value, String label) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(label + " is required");
    }

    private static Set<String> uniqueIds(List<String> values, String label) {
        Set<String> ids = new HashSet<>();
        for (String value : values) if (!ids.add(value)) throw new IllegalArgumentException("duplicate " + label + " id: " + value);
        return ids;
    }
}
