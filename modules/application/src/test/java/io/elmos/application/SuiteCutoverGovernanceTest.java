package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class SuiteCutoverGovernanceTest {
    private final SuiteCutoverGovernance governance = new SuiteCutoverGovernance();

    @Test void financeAndSodAreIndependentHardGates() {
        var gates = new HashSet<>(SuiteCutoverGovernance.cutoverGateNames());
        gates.remove("FINANCIAL_RECONCILED");
        gates.remove("SOD_CLEAR");
        var result = governance.evaluateCutover(evidence(gates), Instant.EPOCH);
        assertEquals(SuiteCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("FINANCIAL_BALANCE_FAILED"));
        assertTrue(result.blockers().contains("SOD_CONFLICT"));
    }

    @Test void artifactDriftMakesEvidenceStale() {
        var evidence = new SuiteCutoverGovernance.Evidence("old", "new", true,
                SuiteCutoverGovernance.cutoverGateNames(), List.of("evidence://suite"));
        assertEquals(SuiteCutoverGovernance.Decision.STALE,
                governance.evaluateCutover(evidence, Instant.EPOCH).decision());
    }

    @Test void cutoverDoesNotPrematurelyRequireLegacyZeroArchiveOrRevocation() {
        assertEquals(SuiteCutoverGovernance.Decision.PASS,
                governance.evaluateCutover(evidence(SuiteCutoverGovernance.cutoverGateNames()), Instant.EPOCH).decision());
    }

    @Test void decommissionRequiresUsageZeroArchiveIdentityLicenseAndLegalHold() {
        var gates = new HashSet<>(SuiteCutoverGovernance.cutoverGateNames());
        gates.addAll(SuiteCutoverGovernance.decommissionGateNames());
        gates.remove("LEGACY_BATCH_ZERO");
        var result = governance.evaluateDecommission(evidence(gates), Instant.EPOCH);
        assertEquals(SuiteCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("LEGACY_BATCH_REMAINS"));
        gates.add("LEGACY_BATCH_ZERO");
        assertEquals(SuiteCutoverGovernance.Decision.PASS,
                governance.evaluateDecommission(evidence(gates), Instant.EPOCH).decision());
    }

    private static SuiteCutoverGovernance.Evidence evidence(Set<String> gates) {
        return new SuiteCutoverGovernance.Evidence("sha", "sha", true, gates, List.of("evidence://suite"));
    }
}
