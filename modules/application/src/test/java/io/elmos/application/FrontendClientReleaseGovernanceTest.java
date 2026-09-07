package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static io.elmos.application.FrontendClientReleaseGovernance.Decision.*;
import static io.elmos.application.FrontendClientReleaseGovernance.Stage.*;
import static org.junit.jupiter.api.Assertions.*;

class FrontendClientReleaseGovernanceTest {
    private final FrontendClientReleaseGovernance governance = new FrontendClientReleaseGovernance();

    @Test void blocksStageSkippingAndMissingEvidence() {
        assertEquals(BLOCKED, governance.evaluate(evidence(NONE, CANARY, true, List.of("ev"), null)).decision());
        assertEquals(HOLD, governance.evaluate(evidence(NONE, INTERNAL, true, List.of(), null)).decision());
    }

    @Test void allClientAndQualityGatesMustPass() {
        assertEquals(HOLD, governance.evaluate(evidence(INTERNAL, CANARY, false, List.of("ev"), null)).decision());
        assertEquals(PROMOTE, governance.evaluate(evidence(INTERNAL, CANARY, true, List.of("ev"), null)).decision());
    }

    @Test void fullAndDecommissionRequireNamedHuman() {
        assertEquals(HUMAN_REVIEW, governance.evaluate(evidence(PROGRESSIVE, FULL, true, List.of("ev"), null)).decision());
        assertEquals(PROMOTE, governance.evaluate(evidence(PROGRESSIVE, FULL, true, List.of("ev"), "release-owner")).decision());
        assertFalse(governance.evaluate(evidence(PROGRESSIVE, FULL, true, List.of("ev"), "release-owner")).automatic());
    }

    @Test void unifiedEvidenceCannotBeEmpty() {
        assertThrows(IllegalArgumentException.class, () -> new FrontendClientReleaseGovernance.EvidenceExtension(
                "org", "elmos.frontend-client-evidence.v1", "artifact://frontend/x", "hash", List.of(), Instant.now()));
    }

    private FrontendClientReleaseGovernance.ReleaseEvidence evidence(
            FrontendClientReleaseGovernance.Stage current,
            FrontendClientReleaseGovernance.Stage requested,
            boolean allPassed, List<String> refs, String approvedBy) {
        return new FrontendClientReleaseGovernance.ReleaseEvidence("org-1", current, requested,
                allPassed, allPassed, allPassed, allPassed, allPassed, allPassed,
                allPassed, allPassed, allPassed, allPassed, refs, approvedBy);
    }
}
