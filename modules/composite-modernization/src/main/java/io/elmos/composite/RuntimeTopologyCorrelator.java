package io.elmos.composite;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

/** Correlates runtime observations with the immutable landscape without erasing static evidence. */
public final class RuntimeTopologyCorrelator {
    private static final Set<String> FORBIDDEN_BAGGAGE_FRAGMENTS = Set.of(
            "password", "secret", "credential", "api_key", "apikey", "access_token", "authorization", "pii");

    public record RuntimeObservation(
            String observationId, String sourceNodeId, String targetNodeId, EdgeType edgeType,
            String environment, EvidenceSource source, String traceId, String spanId,
            String correlationId, String messageId, String causationId, String journeyId,
            String experimentId, Set<String> baggageKeys, Instant observedAt, String evidenceRef,
            double sampleRate) {
        public RuntimeObservation {
            require(observationId, "observationId"); require(sourceNodeId, "sourceNodeId");
            require(targetNodeId, "targetNodeId"); java.util.Objects.requireNonNull(edgeType, "edgeType");
            require(environment, "environment"); java.util.Objects.requireNonNull(source, "source");
            java.util.Objects.requireNonNull(observedAt, "observedAt"); require(evidenceRef, "evidenceRef");
            baggageKeys = immutable(baggageKeys);
            if (sampleRate <= 0 || sampleRate > 1) throw new IllegalArgumentException("sampleRate must be in (0,1]");
            if (source != EvidenceSource.RUNTIME_TRACE && source != EvidenceSource.LOG_CORRELATION
                    && source != EvidenceSource.BROKER_METADATA && source != EvidenceSource.DATABASE_AUDIT) {
                throw new IllegalArgumentException("observation source is not runtime evidence");
            }
        }
    }

    public record CorrelatedEdge(String sourceNodeId, String targetNodeId, EdgeType edgeType,
                                 String environment, double confidence, long observationCount,
                                 List<String> evidenceRefs, boolean declaredAndObserved) {}
    public record CorrelationResult(List<CorrelatedEdge> edges, List<String> conflicts,
                                    double runtimeCoverage, List<String> blockers) {}

    public CorrelationResult correlate(SystemLandscape landscape, List<RuntimeObservation> observations) {
        Map<String, SystemNode> nodes = new LinkedHashMap<>();
        landscape.nodes().forEach(node -> nodes.put(node.nodeId(), node));
        Map<String, List<RuntimeObservation>> grouped = new LinkedHashMap<>();
        Set<String> acceptedRuntimeNodes = new LinkedHashSet<>();
        LinkedHashSet<String> conflicts = new LinkedHashSet<>();
        LinkedHashSet<String> blockers = new LinkedHashSet<>();

        immutable(observations).stream().sorted(Comparator.comparing(RuntimeObservation::observationId)).forEach(observation -> {
            SystemNode source = nodes.get(observation.sourceNodeId());
            SystemNode target = nodes.get(observation.targetNodeId());
            if (source == null || target == null) {
                conflicts.add("RUNTIME_NODE_NOT_IN_LANDSCAPE:" + observation.observationId());
                return;
            }
            if (!source.environment().equals(observation.environment())
                    || !target.environment().equals(observation.environment())) {
                conflicts.add("CROSS_ENVIRONMENT_CORRELATION_REJECTED:" + observation.observationId());
                return;
            }
            for (String key : observation.baggageKeys()) {
                String normalized = key.toLowerCase(Locale.ROOT);
                if (FORBIDDEN_BAGGAGE_FRAGMENTS.stream().anyMatch(normalized::contains)) {
                    blockers.add("SENSITIVE_BAGGAGE_KEY:" + key);
                }
            }
            acceptedRuntimeNodes.add(observation.sourceNodeId());
            acceptedRuntimeNodes.add(observation.targetNodeId());
            grouped.computeIfAbsent(key(observation.sourceNodeId(), observation.targetNodeId(),
                    observation.edgeType(), observation.environment()), ignored -> new ArrayList<>()).add(observation);
        });

        List<CorrelatedEdge> result = new ArrayList<>();
        for (DependencyEdge declared : landscape.edges()) {
            String key = key(declared.sourceNodeId(), declared.targetNodeId(), declared.edgeType(), declared.environment());
            List<RuntimeObservation> runtime = grouped.remove(key);
            List<String> refs = new ArrayList<>(declared.evidence().stream().map(EdgeEvidence::evidenceRef).toList());
            if (runtime == null || runtime.isEmpty()) {
                result.add(new CorrelatedEdge(declared.sourceNodeId(), declared.targetNodeId(), declared.edgeType(),
                        declared.environment(), declared.confidence(), declared.observationCount(), List.copyOf(refs), false));
                continue;
            }
            refs.addAll(runtime.stream().map(RuntimeObservation::evidenceRef).toList());
            result.add(new CorrelatedEdge(declared.sourceNodeId(), declared.targetNodeId(), declared.edgeType(),
                    declared.environment(), Math.max(.95, declared.confidence()), runtime.size(), List.copyOf(refs), true));
        }
        for (List<RuntimeObservation> runtime : grouped.values()) {
            RuntimeObservation first = runtime.getFirst();
            double confidence = runtime.size() >= 2 ? .90 : confidence(first.source());
            result.add(new CorrelatedEdge(first.sourceNodeId(), first.targetNodeId(), first.edgeType(),
                    first.environment(), confidence, runtime.size(),
                    runtime.stream().map(RuntimeObservation::evidenceRef).toList(), false));
        }
        result.sort(Comparator.comparing(CorrelatedEdge::sourceNodeId)
                .thenComparing(CorrelatedEdge::targetNodeId).thenComparing(edge -> edge.edgeType().name()));
        double coverage = nodes.isEmpty() ? 0 : Math.min(1, acceptedRuntimeNodes.size() / (double) nodes.size());
        if (coverage < 1) blockers.add("RUNTIME_TOPOLOGY_COVERAGE_INCOMPLETE");
        return new CorrelationResult(List.copyOf(result), List.copyOf(conflicts), coverage, List.copyOf(blockers));
    }

    private double confidence(EvidenceSource source) {
        return switch (source) {
            case RUNTIME_TRACE -> .85;
            case BROKER_METADATA, DATABASE_AUDIT -> .75;
            case LOG_CORRELATION -> .50;
            default -> .50;
        };
    }

    private String key(String source, String target, EdgeType type, String environment) {
        return source + "\u0000" + target + "\u0000" + type + "\u0000" + environment;
    }
}
