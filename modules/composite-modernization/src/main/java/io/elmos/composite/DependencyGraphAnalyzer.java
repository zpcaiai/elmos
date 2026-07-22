package io.elmos.composite;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class DependencyGraphAnalyzer {
    public record CompositeUnit(String unitId, List<String> nodeIds, boolean compatibilityRuntimeRequired) {}
    public record SharedDatabaseCoupling(String dataNodeId, List<String> writers, List<String> evidenceRefs) {}
    public record Analysis(List<CompositeUnit> cycles, List<SharedDatabaseCoupling> sharedDatabases,
                           List<String> externalOrUnknownConsumers, List<String> blockers) {}

    public Analysis analyze(SystemLandscape landscape) {
        Map<String,SystemNode> nodes = landscape.nodes().stream().collect(java.util.stream.Collectors.toMap(
                SystemNode::nodeId, node -> node));
        List<CompositeUnit> cycles = stronglyConnected(landscape.nodes(), landscape.edges()).stream()
                .filter(component -> component.size() > 1 || hasSelfLoop(component, landscape.edges()))
                .map(component -> new CompositeUnit(CompositeIds.id("composite-unit", component), component, true))
                .sorted(Comparator.comparing(CompositeUnit::unitId)).toList();
        Map<String,List<DependencyEdge>> writers = landscape.edges().stream()
                .filter(edge -> edge.edgeType() == EdgeType.WRITES_DATABASE && edge.hardDependency())
                .collect(java.util.stream.Collectors.groupingBy(DependencyEdge::targetNodeId));
        List<SharedDatabaseCoupling> shared = writers.entrySet().stream()
                .filter(entry -> entry.getValue().stream().map(DependencyEdge::sourceNodeId).distinct().count() > 1)
                .map(entry -> new SharedDatabaseCoupling(entry.getKey(),
                        entry.getValue().stream().map(DependencyEdge::sourceNodeId).distinct().sorted().toList(),
                        entry.getValue().stream().flatMap(edge -> edge.evidence().stream())
                                .map(EdgeEvidence::evidenceRef).distinct().sorted().toList()))
                .sorted(Comparator.comparing(SharedDatabaseCoupling::dataNodeId)).toList();
        List<String> external = landscape.edges().stream().map(DependencyEdge::targetNodeId)
                .filter(id -> nodes.get(id).nodeType() == NodeType.EXTERNAL_SYSTEM)
                .distinct().sorted().toList();
        List<String> blockers = new ArrayList<>();
        if (!shared.isEmpty()) blockers.add("SHARED_DATABASE_COUPLING");
        if (!external.isEmpty()) blockers.add("UNKNOWN_OR_EXTERNAL_CONSUMER");
        if (!cycles.isEmpty()) blockers.add("DEPENDENCY_CYCLE_REQUIRES_COMPOSITE_UNIT");
        if (!landscape.complete()) blockers.add("LANDSCAPE_INCOMPLETE");
        return new Analysis(cycles, shared, external, List.copyOf(blockers));
    }

    public List<List<String>> stronglyConnected(Collection<SystemNode> nodes, Collection<DependencyEdge> edges) {
        Map<String,List<String>> graph = new LinkedHashMap<>();
        nodes.stream().map(SystemNode::nodeId).sorted().forEach(id -> graph.put(id, new ArrayList<>()));
        edges.stream().filter(DependencyEdge::hardDependency)
                .filter(edge -> edge.validity() == EdgeValidity.ACTIVE || edge.validity() == EdgeValidity.DORMANT)
                .forEach(edge -> graph.computeIfAbsent(edge.sourceNodeId(), ignored -> new ArrayList<>())
                        .add(edge.targetNodeId()));
        graph.values().forEach(values -> values.sort(String::compareTo));
        Tarjan tarjan = new Tarjan(graph);
        return tarjan.components().stream()
                .map(component -> component.stream().sorted().toList())
                .sorted(Comparator.comparing(component -> String.join("|", component))).toList();
    }

    private boolean hasSelfLoop(List<String> component, List<DependencyEdge> edges) {
        if (component.size() != 1) return false;
        String id = component.getFirst();
        return edges.stream().anyMatch(edge -> edge.hardDependency()
                && edge.sourceNodeId().equals(id) && edge.targetNodeId().equals(id));
    }

    private static final class Tarjan {
        private final Map<String,List<String>> graph;
        private final Map<String,Integer> index = new HashMap<>();
        private final Map<String,Integer> low = new HashMap<>();
        private final Set<String> onStack = new HashSet<>();
        private final Deque<String> stack = new ArrayDeque<>();
        private final List<List<String>> components = new ArrayList<>();
        private int next;

        Tarjan(Map<String,List<String>> graph) { this.graph = graph; }

        List<List<String>> components() {
            graph.keySet().stream().sorted().filter(node -> !index.containsKey(node)).forEach(this::visit);
            return List.copyOf(components);
        }

        private void visit(String node) {
            index.put(node, next); low.put(node, next); next++;
            stack.push(node); onStack.add(node);
            for (String target : graph.getOrDefault(node, List.of())) {
                if (!index.containsKey(target)) {
                    visit(target); low.put(node, Math.min(low.get(node), low.get(target)));
                } else if (onStack.contains(target)) {
                    low.put(node, Math.min(low.get(node), index.get(target)));
                }
            }
            if (low.get(node).equals(index.get(node))) {
                Set<String> component = new LinkedHashSet<>();
                String value;
                do { value = stack.pop(); onStack.remove(value); component.add(value); } while (!value.equals(node));
                components.add(List.copyOf(component));
            }
        }
    }
}
