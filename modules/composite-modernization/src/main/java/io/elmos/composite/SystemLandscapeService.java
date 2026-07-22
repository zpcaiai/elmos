package io.elmos.composite;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class SystemLandscapeService {
    public record BuildRequest(
            String organizationId, long previousVersion, Instant observedAt, List<SystemNode> nodes,
            List<DependencyEdge> edges, LandscapeCoverage coverage, List<String> unknowns) {
        public BuildRequest {
            require(organizationId, "organizationId");
            if (previousVersion < 0) throw new IllegalArgumentException("previousVersion cannot be negative");
            Objects.requireNonNull(observedAt, "observedAt"); nodes = immutable(nodes); edges = immutable(edges);
            Objects.requireNonNull(coverage, "coverage"); unknowns = immutable(unknowns);
        }
    }

    public SystemLandscape build(BuildRequest request) {
        List<SystemNode> nodes = request.nodes().stream().sorted(Comparator.comparing(SystemNode::nodeId)).toList();
        List<DependencyEdge> edges = request.edges().stream().sorted(Comparator.comparing(DependencyEdge::edgeId)).toList();
        if (nodes.isEmpty()) throw new IllegalArgumentException("landscape requires nodes");
        Set<String> ids = new HashSet<>();
        for (SystemNode node : nodes) {
            if (!request.organizationId().equals(node.organizationId())) throw new IllegalArgumentException("cross-tenant node");
            if (!ids.add(node.nodeId())) throw new IllegalArgumentException("duplicate nodeId: " + node.nodeId());
        }
        for (DependencyEdge edge : edges) {
            if (!request.organizationId().equals(edge.organizationId())) throw new IllegalArgumentException("cross-tenant edge");
            if (!ids.contains(edge.sourceNodeId()) || !ids.contains(edge.targetNodeId())) {
                throw new IllegalArgumentException("edge references a node outside this landscape");
            }
            if (edge.evidence().stream().anyMatch(item -> !edge.environment().equals(item.environment()))) {
                throw new IllegalArgumentException("edge evidence environment mismatch");
            }
        }
        List<String> unknowns = new ArrayList<>(request.unknowns());
        if (request.coverage().minimum() < 1) unknowns.add("LANDSCAPE_COVERAGE_INCOMPLETE");
        if (edges.stream().anyMatch(edge -> edge.validity() == EdgeValidity.SUSPECTED
                || edge.validity() == EdgeValidity.UNVERIFIED)) unknowns.add("UNVERIFIED_DEPENDENCY_PRESENT");
        unknowns = unknowns.stream().distinct().sorted().toList();
        long version = request.previousVersion() + 1;
        String landscapeId = CompositeIds.id("landscape", request.organizationId(), version,
                request.observedAt(), nodes, edges, request.coverage(), unknowns);
        return new SystemLandscape(landscapeId, request.organizationId(), version, request.observedAt(),
                nodes, edges, request.coverage(), unknowns, unknowns.isEmpty());
    }

    public SystemLandscape nextVersion(SystemLandscape previous, Instant observedAt,
                                       List<SystemNode> nodes, List<DependencyEdge> edges,
                                       LandscapeCoverage coverage, List<String> unknowns) {
        Objects.requireNonNull(previous, "previous");
        if (!observedAt.isAfter(previous.observedAt())) {
            throw new IllegalArgumentException("new landscape version must have a later observation time");
        }
        return build(new BuildRequest(previous.organizationId(), previous.version(), observedAt,
                nodes, edges, coverage, unknowns));
    }
}
