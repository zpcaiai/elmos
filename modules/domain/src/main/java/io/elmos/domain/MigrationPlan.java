package io.elmos.domain;

import java.time.Clock;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class MigrationPlan {
    public enum Status { DRAFT, APPROVED, SUPERSEDED }
    public record Step(String id, String executorType, List<String> dependencies, boolean approvalRequired) {
        public Step { id = Identifiers.require(id, "step.id"); executorType = Identifiers.require(executorType, "step.executorType"); dependencies = List.copyOf(dependencies == null ? List.of() : dependencies); }
    }
    private final MigrationPlanId id; private final OrganizationId organizationId; private final SnapshotId snapshotId;
    private final int version; private final String sourceProfile; private final String targetProfile; private final List<Step> steps;
    private Status status = Status.DRAFT; private Instant approvedAt; private String approvedBy;
    public MigrationPlan(MigrationPlanId id, OrganizationId organizationId, SnapshotId snapshotId, int version, String sourceProfile, String targetProfile, List<Step> steps) {
        if (id == null || organizationId == null || snapshotId == null) throw new IllegalArgumentException("plan ids are required");
        if (version < 1) throw new IllegalArgumentException("version must be positive");
        if (steps == null || steps.isEmpty()) throw new IllegalArgumentException("at least one step is required");
        var ids = new HashSet<String>(); for (var step : steps) if (!ids.add(step.id())) throw new IllegalArgumentException("duplicate step id: " + step.id());
        for (var step : steps) if (!ids.containsAll(step.dependencies())) throw new IllegalArgumentException("unknown dependency in step " + step.id());
        rejectDependencyCycles(steps);
        this.id=id; this.organizationId=organizationId; this.snapshotId=snapshotId; this.version=version; this.sourceProfile=Identifiers.require(sourceProfile,"sourceProfile"); this.targetProfile=Identifiers.require(targetProfile,"targetProfile"); this.steps=List.copyOf(steps);
    }

    private static void rejectDependencyCycles(List<Step> steps) {
        Map<String, List<String>> dependencies = new HashMap<>();
        for (var step : steps) dependencies.put(step.id(), step.dependencies());
        var visiting = new HashSet<String>();
        var visited = new HashSet<String>();
        for (var step : steps) visit(step.id(), dependencies, visiting, visited);
    }

    private static void visit(String stepId, Map<String, List<String>> dependencies,
                              Set<String> visiting, Set<String> visited) {
        if (visited.contains(stepId)) return;
        if (!visiting.add(stepId)) throw new IllegalArgumentException("cyclic dependency at step " + stepId);
        for (var dependency : dependencies.get(stepId)) visit(dependency, dependencies, visiting, visited);
        visiting.remove(stepId);
        visited.add(stepId);
    }
    public void approve(String actorId, Clock clock) { if (status != Status.DRAFT) throw new DomainException("only a draft plan can be approved"); approvedBy=Identifiers.require(actorId,"actorId"); approvedAt=clock.instant(); status=Status.APPROVED; }
    public MigrationPlanId id(){return id;} public OrganizationId organizationId(){return organizationId;} public SnapshotId snapshotId(){return snapshotId;} public int version(){return version;} public String sourceProfile(){return sourceProfile;} public String targetProfile(){return targetProfile;} public List<Step> steps(){return steps;} public Status status(){return status;} public Instant approvedAt(){return approvedAt;} public String approvedBy(){return approvedBy;}
}
