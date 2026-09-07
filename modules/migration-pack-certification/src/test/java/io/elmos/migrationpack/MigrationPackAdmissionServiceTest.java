package io.elmos.migrationpack;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static io.elmos.migrationpack.MigrationPackModels.*;
import static org.junit.jupiter.api.Assertions.*;

class MigrationPackAdmissionServiceTest {
    private static final Instant NOW = Instant.parse("2026-07-22T00:00:00Z");
    private static final String SOURCE = "a".repeat(64);
    private static final String TARGET = "b".repeat(64);

    @Test void catalogPreservesAllSixIndependentCertificationDomains() {
        assertEquals(List.of(29, 30, 31, 32, 33, 34), MigrationPackCatalog.all().stream().map(PackDefinition::pack).toList());
        assertEquals(124, MigrationPackCatalog.all().stream().mapToInt(PackDefinition::skillCount).sum());
        assertEquals(38, MigrationPackCatalog.all().stream().mapToInt(PackDefinition::schemaCount).sum());
    }

    @Test void absentRealEvidenceRemainsBlockedAndNotCertified() {
        AdmissionResult result = new MigrationPackAdmissionService().evaluate(request(29, List.of()));
        assertEquals(AdmissionDecision.BLOCKED, result.decision());
        assertFalse(result.certified());
        assertFalse(result.productionMutationExecuted());
        assertTrue(result.blockers().stream().allMatch(value -> value.endsWith("NOT_RUN")));
    }

    @Test void completeEvidenceCanOnlyProceedToTheNamedScriptGate() {
        PackDefinition definition = MigrationPackCatalog.require(34);
        List<PhaseEvidence> evidence = definition.requiredPhases().stream().map(MigrationPackAdmissionServiceTest::evidence).toList();
        AdmissionResult result = new MigrationPackAdmissionService().evaluate(request(34, evidence));
        assertEquals(AdmissionDecision.READY_FOR_PACK_GATE, result.decision());
        assertEquals("scripts/batch34/run_portfolio_gate.py", result.soleCertificationAuthority());
        assertFalse(result.certified());
    }

    @Test void permissiveOrSyntheticEvidenceCannotReachTheGate() {
        PackDefinition definition = MigrationPackCatalog.require(31);
        List<PhaseEvidence> evidence = definition.requiredPhases().stream().map(phase -> new PhaseEvidence(
                phase, EvidenceStatus.PASSED, "org", "assessment", SOURCE, TARGET, "v1", "same-executor",
                false, false, false, false, false, 1, 1, NOW.minusSeconds(1), List.of(), false)).toList();
        AdmissionResult result = new MigrationPackAdmissionService().evaluate(request(31, evidence));
        assertEquals(AdmissionDecision.BLOCKED, result.decision());
        assertTrue(result.blockers().stream().anyMatch(value -> value.endsWith("INDEPENDENT_JUDGE_REQUIRED")));
        assertTrue(result.blockers().stream().anyMatch(value -> value.endsWith("UNSUPPORTED_SEMANTICS_PRESENT")));
    }

    @Test void admissionEvidenceCannotClaimAProductionMutation() {
        assertThrows(IllegalArgumentException.class, () -> new PhaseEvidence("X", EvidenceStatus.PASSED,
                "org", "assessment", SOURCE, TARGET, "v1", "judge", true, true,
                true, true, true, 0, 0, NOW, List.of("ev"), true));
    }

    private static AdmissionRequest request(int pack, List<PhaseEvidence> evidence) {
        return new AdmissionRequest(pack, "org", "assessment", SOURCE, TARGET, "v1", "human", NOW, evidence);
    }
    private static PhaseEvidence evidence(String phase) {
        return new PhaseEvidence(phase, EvidenceStatus.PASSED, "org", "assessment", SOURCE, TARGET,
                "v1", "independent-holdout-judge", true, true, true, true, true,
                0, 0, NOW.minusSeconds(1), List.of("sha256:ev"), false);
    }
}
