package io.elmos.testquality;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class QualityDomainModelsTest {
    @Test void testIdentityRequiresCrossRunDimensions() {
        var identity = new QualityDomainModels.TestCaseIdentity("id", "repo", "module", "JUnit", "suite", "Class", "scenario", List.of("p=1"), "jdk21");
        assertEquals("jdk21", identity.environmentProfile());
        assertThrows(IllegalArgumentException.class, () -> new QualityDomainModels.TestCaseIdentity("id", "repo", "", "JUnit", "suite", "Class", "scenario", List.of(), "jdk21"));
    }

    @Test void countReconciliationKeepsAllFourCountsSeparate() {
        assertFalse(new QualityDomainModels.TestCountReconciliation(10, 9, 9, 9, List.of("TEST_COUNT_REGRESSION")).reconciled());
    }

    @Test void environmentMustDefaultDenyNetwork() {
        assertThrows(IllegalArgumentException.class, () -> new QualityDomainModels.EnvironmentLease("lease", "template", "ns", "ALLOW", Instant.MAX, false, List.of()));
    }

    @Test void workerCannotCreateDecisionThatModifiedGate() {
        assertThrows(IllegalArgumentException.class, () -> new QualityDomainModels.QualityDecision("scope", QualityModels.GateStatus.PASS,
                QualityModels.Confidence.HIGH, "hash", List.of(), List.of(), true));
    }
}
