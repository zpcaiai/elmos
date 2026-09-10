package io.elmos.worker.xml;

import io.elmos.worker.xml.SpringXmlToJavaConfigConverter.BeanDefinition;
import io.elmos.worker.xml.SpringXmlToJavaConfigConverter.ConstructorArgDefinition;
import io.elmos.worker.xml.SpringXmlToJavaConfigConverter.PropertyDefinition;

import java.util.*;

/**
 * Dependency Graph analyzer for Spring Bean XML definitions.
 *
 * <p>Constructs a Directed Acyclic Graph (DAG) of bean dependencies,
 * computes topological initialization order, detects circular references,
 * and proposes @Lazy / ObjectProvider resolution boundaries.
 */
public final class SpringXmlDependencyGraph {

    public record DependencyEdge(String fromBeanId, String toBeanId, EdgeType type) {
        public enum EdgeType {
            CONSTRUCTOR,
            PROPERTY,
            LOOKUP
        }
    }

    public record GraphResolutionResult(
            List<String> topologicalOrder,
            List<DependencyEdge> circularDependencies,
            Set<String> lazyCandidateBeanIds,
            boolean hasCycles
    ) {}

    private final Map<String, BeanDefinition> beanRegistry = new LinkedHashMap<>();
    private final Map<String, Set<String>> adjacencyList = new LinkedHashMap<>();
    private final List<DependencyEdge> allEdges = new ArrayList<>();

    public SpringXmlDependencyGraph(List<BeanDefinition> beans) {
        for (BeanDefinition b : beans) {
            beanRegistry.put(b.id(), b);
            adjacencyList.put(b.id(), new LinkedHashSet<>());
        }
        buildGraph();
    }

    private void buildGraph() {
        for (BeanDefinition bean : beanRegistry.values()) {
            String beanId = bean.id();

            // 1. Constructor dependencies: arg.ref() must be created BEFORE beanId
            if (bean.constructorArgs() != null) {
                for (ConstructorArgDefinition arg : bean.constructorArgs()) {
                    if (arg.ref() != null && !arg.ref().isBlank()) {
                        addEdge(arg.ref(), beanId, DependencyEdge.EdgeType.CONSTRUCTOR);
                    }
                }
            }

            // 2. Property dependencies: prop.ref() should ideally be created BEFORE beanId
            if (bean.properties() != null) {
                for (PropertyDefinition prop : bean.properties()) {
                    if (prop.ref() != null && !prop.ref().isBlank()) {
                        addEdge(prop.ref(), beanId, DependencyEdge.EdgeType.PROPERTY);
                    }
                }
            }
        }
    }

    private void addEdge(String dependency, String dependent, DependencyEdge.EdgeType type) {
        if (beanRegistry.containsKey(dependency) && beanRegistry.containsKey(dependent)) {
            adjacencyList.computeIfAbsent(dependency, k -> new LinkedHashSet<>()).add(dependent);
            allEdges.add(new DependencyEdge(dependency, dependent, type));
        }
    }

    /**
     * Resolves topological order and circular dependencies.
     */
    public GraphResolutionResult resolve() {
        List<String> order = new ArrayList<>();
        List<DependencyEdge> circularEdges = new ArrayList<>();
        Set<String> lazyCandidates = new LinkedHashSet<>();

        // In-degree calculation for Kahn's algorithm
        Map<String, Integer> inDegree = new LinkedHashMap<>();
        for (String id : beanRegistry.keySet()) {
            inDegree.put(id, 0);
        }

        for (Set<String> dependents : adjacencyList.values()) {
            for (String dep : dependents) {
                inDegree.put(dep, inDegree.getOrDefault(dep, 0) + 1);
            }
        }

        Queue<String> queue = new ArrayDeque<>();
        for (Map.Entry<String, Integer> entry : inDegree.entrySet()) {
            if (entry.getValue() == 0) {
                queue.add(entry.getKey());
            }
        }

        while (!queue.isEmpty()) {
            String node = queue.poll();
            order.add(node);

            for (String dependent : adjacencyList.getOrDefault(node, Collections.emptySet())) {
                int updated = inDegree.get(dependent) - 1;
                inDegree.put(dependent, updated);
                if (updated == 0) {
                    queue.add(dependent);
                }
            }
        }

        boolean hasCycles = order.size() < beanRegistry.size();
        if (hasCycles) {
            // Collect unvisited nodes that form cycles
            Set<String> cycleNodes = new LinkedHashSet<>(beanRegistry.keySet());
            cycleNodes.removeAll(order);

            for (DependencyEdge edge : allEdges) {
                if (cycleNodes.contains(edge.fromBeanId()) && cycleNodes.contains(edge.toBeanId())) {
                    circularEdges.add(edge);
                    // Dependent bean can have @Lazy on setter/constructor injection
                    lazyCandidates.add(edge.toBeanId());
                }
            }

            // Append remaining nodes in registry order
            order.addAll(cycleNodes);
        }

        return new GraphResolutionResult(
                Collections.unmodifiableList(order),
                Collections.unmodifiableList(circularEdges),
                Collections.unmodifiableSet(lazyCandidates),
                hasCycles
        );
    }
}
