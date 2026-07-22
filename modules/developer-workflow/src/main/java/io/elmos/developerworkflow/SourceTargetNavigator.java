package io.elmos.developerworkflow;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class SourceTargetNavigator {
    private final String sourceDigest;
    private final String targetDigest;
    private final Map<String, SourceNode> nodes;
    private final List<SourceEdge> edges;

    public SourceTargetNavigator(String sourceDigest, String targetDigest,
                                 List<SourceNode> nodes, List<SourceEdge> edges) {
        this.sourceDigest = requireDigest(sourceDigest);
        this.targetDigest = requireDigest(targetDigest);
        this.nodes = List.copyOf(nodes).stream().collect(Collectors.toUnmodifiableMap(SourceNode::nodeId, Function.identity()));
        this.edges = List.copyOf(edges);
        if (this.nodes.values().stream().anyMatch(node -> !safe(node.path()) || node.startLine() < 1 || node.endLine() < node.startLine())) {
            throw new IllegalArgumentException("unsafe navigation node");
        }
    }

    public NavigationResult navigate(String nodeId, String actualSourceDigest, String actualTargetDigest,
                                     double minimumConfidence) {
        if (!sourceDigest.equals(actualSourceDigest) || !targetDigest.equals(actualTargetDigest)) {
            return new NavigationResult(Decision.DENY, "STALE_NAVIGATION_MAP", List.of(), List.of());
        }
        if (!nodes.containsKey(nodeId)) return new NavigationResult(Decision.ESCALATE, "SOURCE_NODE_UNKNOWN", List.of(), List.of());
        List<SourceNode> destinations = new ArrayList<>();
        Set<String> provenance = new LinkedHashSet<>();
        for (SourceEdge edge : edges) {
            String destination = null;
            if (edge.from().equals(nodeId)) destination = edge.to();
            else if (edge.to().equals(nodeId)) destination = edge.from();
            if (destination != null && edge.confidence() >= minimumConfidence && nodes.containsKey(destination)) {
                destinations.add(nodes.get(destination));
                provenance.addAll(edge.provenanceRefs());
            }
        }
        if (destinations.isEmpty()) return new NavigationResult(Decision.ESCALATE, "NO_CONFIDENT_MAPPING", List.of(), List.of());
        return new NavigationResult(Decision.ALLOW, "NAVIGATION_RESOLVED", destinations, List.copyOf(provenance));
    }

    private static boolean safe(String value) {
        Path path=Path.of(value);
        return !path.isAbsolute() && !value.contains("..");
    }
    private static String requireDigest(String value) {
        if (!Digests.exactSha256(value)) throw new IllegalArgumentException("exact digest required");
        return value;
    }
}
