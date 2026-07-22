package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CrossDomainDecisionGovernanceTest {
    private final CrossDomainDecisionGovernance governance = new CrossDomainDecisionGovernance();
    private final Instant now = Instant.parse("2026-07-22T00:00:00Z");

    @Test void completeEvidenceOnlyBecomesReadyForHumanDecision() {
        var evidence = List.of("DATA", "REPRODUCIBILITY", "EVALUATION", "SAFETY", "RESPONSIBLE_AI", "COST").stream()
                .map(gate -> valid(gate, gate)).toList();
        var result = governance.evaluate(new CrossDomainDecisionGovernance.Request("org",
                CrossDomainDecisionGovernance.Domain.AI_PLATFORM, "PRODUCTION_RELEASE", evidence,
                List.of("approval://change-board/42"), true), now);
        assertEquals(CrossDomainDecisionGovernance.Status.READY_FOR_HUMAN_DECISION, result.status());
        assertFalse(result.eligibleForExecution());
        assertFalse(result.humanDecisionGranted());
        assertFalse(result.productionStateChanged());
    }

    @Test void staleNonIndependentOrMissingEvidenceBlocks() {
        var result = governance.evaluate(new CrossDomainDecisionGovernance.Request("org",
                CrossDomainDecisionGovernance.Domain.EDGE_IOT_INDUSTRIAL, "SITE_CUTOVER",
                List.of(new CrossDomainDecisionGovernance.Evidence("e1", "SAFETY", "site-runner",
                        now.minus(2, ChronoUnit.DAYS), now.minus(1, ChronoUnit.DAYS), false, true)),
                List.of(), true), now);
        assertEquals(CrossDomainDecisionGovernance.Status.BLOCKED, result.status());
        assertTrue(result.missingGates().contains("INDEPENDENT_HUMAN_APPROVAL"));
        assertEquals(List.of("e1"), result.rejectedEvidenceRefs());
    }

    private CrossDomainDecisionGovernance.Evidence valid(String ref, String gate) {
        return new CrossDomainDecisionGovernance.Evidence(ref, gate, "independent-judge",
                now.minus(1, ChronoUnit.HOURS), now.plus(1, ChronoUnit.DAYS), true, true);
    }
}
