package io.elmos.application;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class IntegrationCutoverGovernanceTest {
    private final IntegrationCutoverGovernance governance = new IntegrationCutoverGovernance();

    @Test void cutoverSeparatesContractDeliveryBusinessAndProducerConsumerReadiness() {
        var e = evidence();
        var missingDelivery = copy(e, false, true, true, true, true, true);
        var result = governance.evaluateCutover(missingDelivery, Instant.EPOCH);
        assertEquals(IntegrationCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("DELIVERY_SEMANTICS_UNKNOWN"));
    }

    @Test void artifactDriftMakesEvidenceStale() {
        var e = evidence();
        var stale = new IntegrationCutoverGovernance.Evidence("old", "new", true,
                true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, List.of("evidence://integration"));
        assertEquals(IntegrationCutoverGovernance.Decision.STALE, governance.evaluateCutover(stale, Instant.EPOCH).decision());
    }

    @Test void cutoverDoesNotPrematurelyRequireLegacyZeroOrCredentialRevocation() {
        var e = evidence();
        var cutoverStage = new IntegrationCutoverGovernance.Evidence(e.sourceArtifact(), e.evaluatedArtifact(), true,
                true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, true, true,
                false, false, false, false, false, false, false, false, e.evidenceRefs());
        assertEquals(IntegrationCutoverGovernance.Decision.PASS, governance.evaluateCutover(cutoverStage, Instant.EPOCH).decision());
    }

    @Test void decommissionRequiresRuntimeZeroRevocationAndArchive() {
        var e = evidence();
        var notRetired = new IntegrationCutoverGovernance.Evidence(e.sourceArtifact(), e.evaluatedArtifact(), true,
                true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, true, true,
                true, false, true, true, true, true, true, true, e.evidenceRefs());
        var result = governance.evaluateDecommission(notRetired, Instant.EPOCH);
        assertEquals(IntegrationCutoverGovernance.Decision.FAIL, result.decision());
        assertTrue(result.blockers().contains("LEGACY_PRODUCER_REMAINS"));
        assertEquals(IntegrationCutoverGovernance.Decision.PASS, governance.evaluateDecommission(e, Instant.EPOCH).decision());
    }

    private static IntegrationCutoverGovernance.Evidence evidence() {
        return new IntegrationCutoverGovernance.Evidence("sha", "sha", true,
                true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, true, true,
                true, true, true, true, true, true, true, true,
                List.of("evidence://integration"));
    }

    private static IntegrationCutoverGovernance.Evidence copy(IntegrationCutoverGovernance.Evidence e,
            boolean delivery, boolean business, boolean producer, boolean consumer, boolean partner, boolean workflow) {
        return new IntegrationCutoverGovernance.Evidence(e.sourceArtifact(), e.evaluatedArtifact(), e.evidenceFresh(),
                true, delivery, business, true, true, producer, consumer, partner, workflow,
                true, true, true, true, true, true, true,
                true, true, true, true, true, true, true, true, e.evidenceRefs());
    }
}
