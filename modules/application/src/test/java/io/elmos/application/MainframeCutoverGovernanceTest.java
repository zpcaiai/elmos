package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MainframeCutoverGovernanceTest {
    private final MainframeCutoverGovernance governance = new MainframeCutoverGovernance();

    @Test void oldBatchWriterBlocksCutover() {
        var e = evidence();
        var changed = new MainframeCutoverGovernance.Evidence(e.sourceArtifact(), e.evaluatedArtifact(), true, true,
                true, true, true, true, true, false, true, true, true, true, true, true, e.evidenceRefs());
        var result = governance.evaluateCutover(changed, Instant.EPOCH);
        assertEquals(MainframeCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("MULTIPLE_DATA_WRITERS"));
        assertFalse(result.workerModifiedRoute());
    }

    @Test void staleArtifactCannotPass() {
        var e = evidence();
        var stale = new MainframeCutoverGovernance.Evidence("old", "new", true, true, true, true, true,
                true, true, true, true, true, true, true, true, true, e.evidenceRefs());
        assertEquals(MainframeCutoverGovernance.Decision.STALE, governance.evaluateCutover(stale, Instant.EPOCH).decision());
    }

    @Test void completeIndependentEvidenceCanAuthorize() {
        var result = governance.evaluateDecommission(evidence(), Instant.EPOCH);
        assertEquals(MainframeCutoverGovernance.Decision.PASS, result.decision());
        assertTrue(result.cutoverAuthorized());
        assertTrue(result.decommissionAuthorized());
    }

    @Test void cutoverDoesNotRequirePrematureUsageZeroOrAccessRevocation() {
        var e = evidence();
        var cutoverStage = new MainframeCutoverGovernance.Evidence(e.sourceArtifact(), e.evaluatedArtifact(), true, true,
                true, true, true, true, true, true, true, false, false, false, false, true, e.evidenceRefs());
        var result = governance.evaluateCutover(cutoverStage, Instant.EPOCH);
        assertEquals(MainframeCutoverGovernance.Decision.PASS, result.decision());
        assertTrue(result.cutoverAuthorized());
        assertFalse(result.decommissionAuthorized());
    }

    private static MainframeCutoverGovernance.Evidence evidence() {
        return new MainframeCutoverGovernance.Evidence("sha", "sha", true, true, true, true, true,
                true, true, true, true, true, true, true, true, true, List.of("evidence://mainframe"));
    }
}
