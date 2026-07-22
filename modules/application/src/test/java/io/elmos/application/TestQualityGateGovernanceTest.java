package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class TestQualityGateGovernanceTest {
    private final TestQualityGateGovernance governance = new TestQualityGateGovernance();

    @Test void failsWhenCriticalRiskHasNoEffectiveTest() {
        var result = governance.evaluate(evidence(1, true, true), Instant.EPOCH);
        assertEquals(TestQualityGateGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("QUALITY_RISK_UNCOVERED"));
        assertFalse(result.releaseAuthorized());
        assertFalse(result.gateModifiedByWorker());
    }

    @Test void staleCommitCannotPass() {
        var result = governance.evaluate(new TestQualityGateGovernance.Evidence("old", "new", true,
                10, 10, 10, 10, 0, 0, 0, 0, 0, true, true, List.of("evidence://1"), Map.of()), Instant.EPOCH);
        assertEquals(TestQualityGateGovernance.Decision.STALE, result.decision());
    }

    @Test void freshCompleteEvidenceCanPass() {
        assertEquals(TestQualityGateGovernance.Decision.PASS,
                governance.evaluate(evidence(0, true, true), Instant.EPOCH).decision());
    }

    private TestQualityGateGovernance.Evidence evidence(int risks, boolean fidelity, boolean fresh) {
        return new TestQualityGateGovernance.Evidence("sha", "sha", true, 10, 10, 10, 10,
                0, risks, 0, 0, 0, fidelity, fresh, List.of("evidence://quality"), Map.of());
    }
}
