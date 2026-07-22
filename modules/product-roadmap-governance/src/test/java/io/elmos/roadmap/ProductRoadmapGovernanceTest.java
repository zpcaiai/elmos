package io.elmos.roadmap;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static io.elmos.roadmap.ProductRoadmapModels.*;
import static org.junit.jupiter.api.Assertions.*;

class ProductRoadmapGovernanceTest {
    private static final Instant NOW = Instant.parse("2026-07-22T00:00:00Z");
    private static final String DIGEST = "a".repeat(64);

    @Test void catalogCoversEveryCommercialProductBatchWithoutConflatingMigrationPacks() {
        var all = ProductRoadmapCatalog.all();
        assertEquals(List.of(27, 28, 29, 30, 31, 32, 33, 34), all.stream().map(BatchDefinition::batch).toList());
        assertEquals(18, ProductRoadmapCatalog.require(27).runtimeSkillCount());
        assertEquals(35, ProductRoadmapCatalog.require(33).runtimeSkillCount());
        assertEquals(40, ProductRoadmapCatalog.require(34).runtimeSkillCount());
        assertEquals(20, ProductRoadmapCatalog.require(34).acceptanceScenarioCount());
    }

    @Test void missingExternalEvidenceIsExplicitlyNotRun() {
        EvaluationResult result = new ProductRoadmapGovernance().evaluate(request(27, List.of()));
        assertEquals(Decision.BLOCKED, result.decision());
        assertEquals("BLOCKED", result.highestGate());
        assertTrue(result.gates().stream().allMatch(value -> value.status() == EvidenceStatus.NOT_RUN));
        assertFalse(result.humanApprovalGranted());
        assertFalse(result.externalOperationExecuted());
    }

    @Test void completeIndependentEvidenceOnlyPreparesAHumanDecision() {
        BatchDefinition definition = ProductRoadmapCatalog.require(34);
        List<GateEvidence> evidence = definition.gates().stream().map(gate -> evidence(gate.id(), true, DIGEST)).toList();
        EvaluationResult result = new ProductRoadmapGovernance().evaluate(request(34, evidence));
        assertEquals(Decision.READY_FOR_HUMAN_DECISION, result.decision());
        assertEquals(definition.finalGate(), result.highestGate());
        assertTrue(result.evidenceComplete());
        assertTrue(result.humanApprovalRequired());
        assertFalse(result.humanApprovalGranted());
    }

    @Test void snapshotMismatchAndNonIndependentJudgeFailClosed() {
        BatchDefinition definition = ProductRoadmapCatalog.require(33);
        List<GateEvidence> evidence = definition.gates().stream()
                .map(gate -> evidence(gate.id(), false, "b".repeat(64))).toList();
        EvaluationResult result = new ProductRoadmapGovernance().evaluate(request(33, evidence));
        assertEquals(Decision.BLOCKED, result.decision());
        assertTrue(result.blockers().stream().anyMatch(value -> value.endsWith("SNAPSHOT_MISMATCH")));
        assertTrue(result.blockers().stream().anyMatch(value -> value.endsWith("INDEPENDENT_JUDGE_REQUIRED")));
    }

    @Test void evidenceCannotClaimThatGovernanceExecutedTheExternalOperation() {
        assertThrows(IllegalArgumentException.class, () -> new GateEvidence("X", EvidenceStatus.PASSED,
                "org", "run", DIGEST, "p1", "authority", true, 1, 0, NOW, List.of("ev"), true));
    }

    private static EvaluationRequest request(int batch, List<GateEvidence> evidence) {
        return new EvaluationRequest(batch, "org", "run", DIGEST, "p1", "human", NOW, evidence);
    }
    private static GateEvidence evidence(String gate, boolean independent, String digest) {
        return new GateEvidence(gate, EvidenceStatus.PASSED, "org", "run", digest, "p1",
                "external-independent-judge", independent, 1, 0, NOW.minusSeconds(1), List.of("sha256:ev"), false);
    }
}
