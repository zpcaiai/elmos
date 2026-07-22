package io.elmos.composite;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.composite.CompatibilityGovernance.*;
import static io.elmos.composite.CompositeModels.*;
import static org.junit.jupiter.api.Assertions.*;

class CompositeGovernanceTest {
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");

    @Test void runtimeCorrelationRejectsCrossEnvironmentAndSensitiveBaggage() {
        SystemLandscape landscape = landscape();
        RuntimeTopologyCorrelator.RuntimeObservation sensitive = new RuntimeTopologyCorrelator.RuntimeObservation(
                "obs-1", "java-api", "python-risk", EdgeType.CALLS_HTTP, "prod",
                EvidenceSource.RUNTIME_TRACE, "trace", "span", "correlation", null, null,
                "checkout", "shadow-1", Set.of("customer.password"), NOW, "trace-ev", 1);
        RuntimeTopologyCorrelator.RuntimeObservation wrongEnvironment = new RuntimeTopologyCorrelator.RuntimeObservation(
                "obs-2", "java-api", "python-risk", EdgeType.CALLS_HTTP, "test",
                EvidenceSource.RUNTIME_TRACE, "trace2", "span2", "correlation2", null, null,
                "checkout", "shadow-1", Set.of(), NOW, "trace-ev-2", 1);

        var result = new RuntimeTopologyCorrelator().correlate(landscape, List.of(sensitive, wrongEnvironment));
        assertTrue(result.blockers().contains("SENSITIVE_BAGGAGE_KEY:customer.password"));
        assertTrue(result.conflicts().contains("CROSS_ENVIRONMENT_CORRELATION_REJECTED:obs-2"));
        assertTrue(result.edges().getFirst().declaredAndObserved());
        assertTrue(result.edges().getFirst().confidence() >= .95);
    }

    @Test void missingRuntimeTraceDoesNotDeleteStaticEdge() {
        var result = new RuntimeTopologyCorrelator().correlate(landscape(), List.of());
        assertEquals(1, result.edges().size());
        assertFalse(result.edges().getFirst().declaredAndObserved());
        assertTrue(result.blockers().contains("RUNTIME_TOPOLOGY_COVERAGE_INCOMPLETE"));
    }

    @Test void incompleteLandscapeCannotClaimCompletenessAndVersionsAreDeterministic() {
        var service = new SystemLandscapeService();
        var nodes = landscape().nodes();
        var partial = new LandscapeCoverage(1, 1, .5, 1, 0, 1, 1, 1);
        var request = new SystemLandscapeService.BuildRequest("org-1", 0, NOW, nodes, List.of(), partial, List.of());
        var first = service.build(request);
        var second = service.build(request);
        assertFalse(first.complete());
        assertEquals(first.landscapeId(), second.landscapeId());
        assertTrue(first.unknowns().contains("LANDSCAPE_COVERAGE_INCOMPLETE"));
    }

    @Test void agentGeneratedAdapterCannotPublishWithoutHumanApproval() {
        AdapterCandidate candidate = new AdapterCandidate("adapter-1", RuntimeType.GRPC_PROXY, "platform",
                NOW.plusSeconds(86400), LossPolicy.LOSSLESS, false, true, true, true,
                true, true, true, false, true, true, true, true, true, true,
                true, true, false, List.of("adapter-ev"));
        AdapterDecision decision = new CompatibilityGovernance().evaluate(candidate, NOW);
        assertFalse(decision.publishAllowed());
        assertTrue(decision.blockers().contains("AGENT_CANDIDATE_NOT_APPROVED"));
    }

    @Test void evidenceMappingIsDeterministicAndPreservesLanguageEvidence() {
        CompositeEvidenceMapper mapper = new CompositeEvidenceMapper();
        var one = mapper.map("org-1", "SYSTEM_LANDSCAPE", "landscape-1", "READY",
                Map.of("version", 1), NOW, List.of("python-ev", "java-ev", "java-ev"));
        var two = mapper.map("org-1", "SYSTEM_LANDSCAPE", "landscape-1", "READY",
                Map.of("version", 1), NOW, List.of("python-ev", "java-ev", "java-ev"));
        assertEquals(one.contentHash(), two.contentHash());
        assertEquals(List.of("java-ev", "python-ev"), one.languageEvidenceRefs());
        assertEquals("COMPOSITE_SYSTEM", one.scope());
    }

    private SystemLandscape landscape() {
        SystemNode java = new SystemNode("java-api", "org-1", NodeType.SERVICE, "Java API", Language.JAVA,
                "repo-java", "deploy-java", "prod", List.of("node-java-ev"));
        SystemNode python = new SystemNode("python-risk", "org-1", NodeType.MODEL_ENDPOINT, "Python Risk", Language.PYTHON,
                "repo-python", "deploy-python", "prod", List.of("node-python-ev"));
        EdgeEvidence evidence = new EdgeEvidence("static-edge-ev", EvidenceSource.STATIC_SOURCE,
                NOW.minusSeconds(60), "prod", CompositeIds.hash("static-edge"));
        DependencyEdge edge = new DependencyEdge("edge-1", "org-1", "java-api", "python-risk",
                EdgeType.CALLS_HTTP, "prod", .8, NOW.minusSeconds(60), NOW, 1,
                EdgeValidity.ACTIVE, List.of(evidence), true, "risk-openapi-v1");
        return new SystemLandscapeService().build(new SystemLandscapeService.BuildRequest("org-1", 0, NOW,
                List.of(java, python), List.of(edge), new LandscapeCoverage(1, 1, 1, 1, 1, 1, 1, 1), List.of()));
    }
}
