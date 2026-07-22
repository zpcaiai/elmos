package io.elmos.composite;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;
import static io.elmos.composite.ContractCatalogService.Compatibility;

public final class MigrationWavePlanner {
    public enum ConstraintType {
        MUST_PRECEDE, MUST_FOLLOW, MUST_MIGRATE_WITH, MUST_NOT_OVERLAP,
        REQUIRES_COMPATIBILITY_WINDOW, REQUIRES_DATA_SYNC, REQUIRES_EXTERNAL_CONSUMER
    }
    public record Constraint(String fromNodeId, String toNodeId, ConstraintType type, String evidenceRef) {}
    public record Wave(int number, String purpose, List<String> nodeIds, List<String> prerequisites) {}
    public record CompositePlan(String planId, String landscapeId, List<Wave> waves,
                                List<DependencyGraphAnalyzer.CompositeUnit> compositeUnits,
                                List<Constraint> constraints, List<String> blockers,
                                boolean repositoryPlansTraceable) {}

    public CompositePlan plan(SystemLandscape landscape, Map<String,Compatibility> compatibilityByEdge,
                              List<DataOwnership> ownership, List<Constraint> requestedConstraints,
                              Set<String> highRiskNodes, Set<String> repositoryPlanNodeIds) {
        Objects.requireNonNull(landscape, "landscape");
        DependencyGraphAnalyzer.Analysis analysis = new DependencyGraphAnalyzer().analyze(landscape);
        List<Constraint> constraints = new ArrayList<>(immutable(requestedConstraints));
        for (DependencyEdge edge : landscape.edges()) {
            Compatibility compatibility = compatibilityByEdge.getOrDefault(edge.edgeId(), Compatibility.UNKNOWN);
            if (compatibility == Compatibility.BREAKING) {
                constraints.add(new Constraint(edge.sourceNodeId(), edge.targetNodeId(),
                        ConstraintType.MUST_MIGRATE_WITH, edge.contractRef()));
            } else if (compatibility == Compatibility.BACKWARD || compatibility == Compatibility.FULL) {
                constraints.add(new Constraint(edge.targetNodeId(), edge.sourceNodeId(),
                        ConstraintType.MUST_PRECEDE, edge.contractRef()));
            } else if (compatibility == Compatibility.FORWARD) {
                constraints.add(new Constraint(edge.sourceNodeId(), edge.targetNodeId(),
                        ConstraintType.MUST_PRECEDE, edge.contractRef()));
            } else {
                constraints.add(new Constraint(edge.sourceNodeId(), edge.targetNodeId(),
                        ConstraintType.REQUIRES_COMPATIBILITY_WINDOW, edge.contractRef()));
            }
        }
        ownership.forEach(item -> {
            if (item.state() != OwnershipState.NEW_AUTHORITATIVE && item.state() != OwnershipState.DECOMMISSIONED) {
                constraints.add(new Constraint(item.authoritativeWriter(), item.dataAssetId(),
                        ConstraintType.REQUIRES_DATA_SYNC, item.evidenceRefs().getFirst()));
            }
        });
        Set<String> consumers = landscape.edges().stream().map(DependencyEdge::sourceNodeId)
                .collect(java.util.stream.Collectors.toSet());
        Set<String> producers = landscape.edges().stream().map(DependencyEdge::targetNodeId)
                .collect(java.util.stream.Collectors.toSet());
        List<String> lowRiskConsumers = consumers.stream().filter(id -> !highRiskNodes.contains(id))
                .filter(id -> landscape.nodes().stream().anyMatch(node -> node.nodeId().equals(id)
                        && node.nodeType() != NodeType.DATABASE && node.nodeType() != NodeType.TABLE))
                .sorted().toList();
        List<String> coreProducers = producers.stream().filter(id -> !highRiskNodes.contains(id)).sorted().toList();
        List<String> dataNodes = landscape.nodes().stream()
                .filter(node -> node.nodeType() == NodeType.DATABASE || node.nodeType() == NodeType.SCHEMA
                        || node.nodeType() == NodeType.TABLE)
                .map(SystemNode::nodeId).sorted().toList();
        List<Wave> waves = List.of(
                new Wave(0, "OBSERVABILITY_AND_CONTRACTS", List.of(), List.of("LANDSCAPE", "TRACE", "CONTRACT_CATALOG")),
                new Wave(1, "COMPATIBILITY_FOUNDATION", List.of(), List.of("ADAPTERS", "OUTBOX", "CDC", "FLAGS")),
                new Wave(2, "LOW_RISK_CONSUMERS", lowRiskConsumers, List.of("CONSUMER_DUAL_FORMAT_READY")),
                new Wave(3, "PRODUCERS_AND_CORE_SERVICES", coreProducers, List.of("SHADOW", "CANARY")),
                new Wave(4, "DATA_OWNERSHIP", dataNodes, List.of("BACKFILL", "CDC", "RECONCILIATION")),
                new Wave(5, "HIGH_RISK_CORE", highRiskNodes.stream().sorted().toList(), List.of("HUMAN_APPROVAL")),
                new Wave(6, "COMPATIBILITY_REMOVAL_AND_DECOMMISSION", List.of(), List.of("ZERO_OLD_USAGE", "STABILITY_HOLD")));
        LinkedHashSet<String> blockers = new LinkedHashSet<>(analysis.blockers());
        if (compatibilityByEdge.values().stream().anyMatch(value -> value == Compatibility.BREAKING)) {
            blockers.add("BREAKING_CONTRACT_REQUIRES_LOCKSTEP_OR_BRIDGE");
        }
        if (compatibilityByEdge.size() < landscape.edges().size()) blockers.add("CONTRACT_MATRIX_INCOMPLETE");
        boolean traceable = repositoryPlanNodeIds.containsAll(landscape.nodes().stream()
                .filter(node -> node.nodeType() == NodeType.REPOSITORY)
                .map(SystemNode::nodeId).toList());
        if (!traceable) blockers.add("REPOSITORY_PLAN_TRACEABILITY_INCOMPLETE");
        List<Constraint> sortedConstraints = constraints.stream().distinct()
                .sorted(Comparator.comparing(Constraint::fromNodeId).thenComparing(Constraint::toNodeId)
                        .thenComparing(item -> item.type().name())).toList();
        String planId = CompositeIds.id("composite-plan", landscape.landscapeId(), waves,
                analysis.cycles(), sortedConstraints, blockers);
        return new CompositePlan(planId, landscape.landscapeId(), waves, analysis.cycles(),
                sortedConstraints, List.copyOf(blockers), traceable);
    }
}
